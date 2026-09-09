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

## 2026-09-09 — Builder run (`claude/sweet-babbage-pu1q6v` → v0.405.0, v0.405.1): the library-wide "new subs waiting" note, and the bug a CLEAN dogfood was hiding

**The run.** Two shipped items, both in [`SHIPPED.md`](SHIPPED.md): **v0.405.0**
(new beginner feature — `GET /api/new-subs-waiting` + `NewSubsWaitingNote`) and
**v0.405.1** (a friendliness/trust bug on the priority-1 editor). Tests **+20**
(9 Python, 11 frontend); one of the two editor tests was verified **fail-before**
against `795f3c32`.

**Why a feature rather than a backlog item, and how long that took to establish.**
The triage was long because the answer was "nothing here is ready", which takes as
much reading as a hit. Walked the whole of "Bugs (fix these first)" — every open
entry is gated on data no agent has, or is a stand-down that already carries its
measurements — and the four Ideas subsections top-down. Of the entries that read
as live: **"one voice" for the marginal-return sentence** is effectively already
shipped (`readiness.noiseReductionHint` and `nightplan._depth_sentence` compute
`1 − √(t/(t+1))` and round to a whole percent — the same number by the same
formula, so there is nothing to reconcile); the Scout's 2026-09-09 **field-fill
diagram** idea shipped as v0.401.0 the same day it was filed; the **dark/light
exposure mismatch**, the **min/max `k` auto-scale**, the **mixed-pointings
pre-flight** and the **catalog-magnitude difficulty split** all carry closure
notes. So the run took AGENTS.md §1's standing allocation ("ship a genuine
beginner feature on a regular cadence") rather than manufacturing work.

**Dogfood: CLEAN, and that is the point of the second item**
(`scripts/agent-dogfood.sh --mosaic --editor`, then again with `--build` after
the change).
- **Mosaic trim: 7.9 %** of the union canvas — the same figure as the last four
  passes, well under the ~15 % §1 calls a bug.
- **Page probes clean, both samples**, nothing overflowing, no console errors.
  Field: `/life-list` 3,094 px, `/targets/<field>` 3,078 px, editor 3,072 px on a
  phone. Mosaic: target 3,407 px, editor 3,102 px. All in line with the standing
  baselines — **no IA slice indicated (fifth measurement agreeing)**.
- **Editor drive clean on both samples**: all **21** ops added one at a time,
  each re-rendering the live preview, then undo/redo, with no console error and
  no failed request. (The 900 s wall-clock the 2026-09-09 Scout run hit is
  avoidable: the scratch data root persists, so a second pass with `--no-stack`
  reuses the stacked samples and the whole pass finishes in a couple of minutes.)

**The lesson, and it is a new one: a CLEAN dogfood is a statement about
*errors*, not about *sentences*.** The probe checks overflow and the console; it
cannot read. Every finding of this pass came from opening the PNGs it wrote and
*looking* at them — which is how v0.405.1 was found: the **Target** page said
*"It's bigger than **this mosaic** — only about 55% of it is in this picture"*
and the **editor of that same run**, one click away, said *"is bigger than the
Seestar's single frame — shoot it in mosaic mode"*. Two surfaces, one fact,
opposite usefulness, on a target already shot as four panels. Nothing overflowed
and nothing logged, so the pass was reported CLEAN — twice, by two runs.
**Recommendation for future passes: read the screenshots, at least for the
Target page and the editor on the mosaic sample.** They are cheap to look at and
they are the only place the app's *words* are on trial.

**The second-order lesson: the gap was in a rule the code already stated.**
`ObjectInfoCard.hideFraming` documents "on a page carrying both, the prediction
is the copy to drop", and `FramingVerdictNote`'s own comment enumerates the
surfaces — "the Target page hides the catalogue line … and History never renders
that card at all". The **editor** renders that card and was in neither list. When
a comment enumerates the callers of a rule, the enumeration is the thing to
re-grep, not to trust.

**Version collision #14 — the number, not the work.** A concurrent Builder
merged PR #805 (`claude/sweet-babbage-03ba9j`) while this run was testing, and
took **v0.404.0** for its own item. Nothing was duplicated — their two are the
whole-recipe Auto parity guard and the `auto_stack` switch nudge; this run's are
the new-subs note and the editor framing divergence — so this is the cheap kind
of collision, caught by §11's "set the version at merge time, from the latest
`main`". Both of this run's items were **renumbered at merge time to v0.405.0 and
v0.405.1**; the two commit subjects still read `v0.404.0` / `v0.404.1`, because
they were written before the other PR landed and rewriting a pushed branch to fix
a number is the worse trade. **Grep the docs, not the log, for a version.** Their
`AutoStackOffNote` and this run's `NewSubsWaitingNote` both join the Dashboard's
`NoticeBoard` at `advisory`; the conflict was a two-line union and both notes are
on the board.

**Measured, as the standing IA rule demands** (`--build --mosaic --editor`
against the same scratch): the mosaic **editor** goes **2,113 → 2,096 px on
desktop and 3,102 → 3,085 px on a phone — 17 px *shorter* at both widths**,
because the catalogue line and its field-fill diagram (a *pre-capture* "will it
fit in one frame?" picture, equally stale on a mosaic) stand down together, as
they already do on the Target page. The mosaic Target page is byte-identical at
3,407 / 2,104 px. Nothing overflowing, no console errors, trim still 7.9 %.
## 2026-09-09 — Builder run (`claude/sweet-babbage-03ba9j` → v0.403.1, v0.404.0): a whole-recipe Auto parity guard, the auto-stack switch nobody had mentioned, and two clean sweeps

**The run.** Baseline green before any change: **5,433 passed / 2 skipped**, full
suite headless, 27:55. Two shipped items. `scripts/agent-setup.sh` completed
cleanly first time (no repeat of the previous run's half-empty venv).

**How the work was chosen, and what that says about the backlog.** The previous
run's note already recorded that the Bugs section holds no open, ungated bug and
that ~55 Ideas entries survive of which most are measured stand-downs. I
re-extracted every top-level entry across all six sections and confirmed it, then
checked five candidates in the code and closed each on its own terms: the
"faint-field re-solve ladder" and "Try harder to locate these" are both answered
by the 2026-07-24 real-ASTAP audit already in the tree (`_SOLVE_LADDER` is
measured, and every sensitivity lever the entries guess at measured as a
non-lever); slice (c) of the sibling-hint entry reduces, once traced, to "a
hintless frame gets the sibling hint one scan later than it could" — a delay, not
a loss, and structurally unreachable for a Seestar whose subs carry RA/Dec
headers; and the owner-approved `batch_stack_tmp` scan skip (Q5) is **already
built** (`scanner._TEMP_FOLDER_NAMES`, v0.319.6 and its scan-time half). So the
two items shipped came from measuring and from reading the owner's own gate list,
not from the Ideas queue.

**QA SWEEP — whole-recipe Auto preview↔export parity on a mosaic canvas: CLEAN,
and now a permanent test.** `test_edit_proxy_parity.py` measures the A2 class one
op at a time; nothing had ever rendered the eleven-op recipe `auto_recipe`
actually builds. Measured on three mosaic strips at the strides the owner's
canvases reach — worst statistic **0.0034** at `proxy_scale=5` (600x3000),
**0.0043** at 4 (1500x6000), **0.0076** at 8 (900x12000, the heavy-stride regime
where the coverage-levelling floor bug lived until v0.237.2). All inside the ~2 %
decimation floor. Shipped as `tests/test_auto_recipe_proxy_parity.py` (v0.403.1)
with the trap armed on every run: patching `EditContext.scaled_px` to the
identity *is* the A2 defect and moves the same number to **0.1085**, a 32x
separation. The two larger strips are recorded in `SHIPPED.md` rather than run
every time (a native-resolution render pair costs ~11 s).

**DOGFOOD `--mosaic --editor`: CLEAN.** Field and mosaic samples both. Mosaic trim
Auto would apply: **7.9 %** (above ~15 % is a bug, AGENTS.md §1). Nothing
overflowing, no console errors on either target. The editor drive added all 21
ops one at a time on both runs, each re-rendering the live preview, then undo and
redo — clean on both. Phone page heights on the mosaic target: Target 3,407 px,
editor 3,102 px, life list 3,094 px, Dashboard 2,432 px.

**The lesson worth carrying, and it is the third run in a row of the same shape.**
v0.404.0's first draft put its note inside `LastNightCard` — the right *content*
home, where the news of the night is. Nine jsdom assertions passed. A real
browser at 420 px reported the element **hidden**: `LastNightCard` lives inside
the Dashboard's `InsightTabs` "Recent" panel, which is `display: none` until that
tab is clicked. The feature is entirely about discovery, so that placement was
not a polish issue, it was the feature not existing. It moved to the notice
board. **Generalisation:** the previous run wrote *"an assertion that an element
is in the document is not an assertion that it can be read"* — this run's
addition is that it is not an assertion that it is **on screen** either. jsdom
renders every branch of a tab component; only a browser knows which panel is
displayed. Any run adding a surface to a page that groups its content — the
Dashboard's `InsightTabs`, the Target page's — should photograph it before
believing the suite.

**Environment note — a run that does several full suites WILL run out of disk, and
it does not look like a disk problem.** The fourth full `pytest` of this session
died at ~80 % with every later write failing, and the tell was not in the pytest
output at all (the harness could no longer write the log file). `/tmp` held
**28 GB** under `/tmp/pytest-of-root` — pytest keeps the last three runs' `tmp_path`
trees, and this suite's fixtures write real FITS, so each run is ~9 GB. Add the
dogfood scratch (`/tmp/astrostack-dogfood`, sample library + stacked masters +
the on-demand Playwright install) and the container's 252 GB allowance is gone.
`rm -rf /tmp/pytest-of-root` took the disk from 100 % to 26 % in one command and
the re-run was clean. **If a suite starts failing late in a long run, check `df -h /`
before reading the failure** — and delete the dogfood scratch when the pass is
over, since its screenshots are the only part worth keeping.

**Also worth recording: the backlog's own "REQUIRES MANUAL OWNER ACTION" list was
actionable after all.** Item 2 ("flip Auto-stack on yourself") had sat there since
v0.391.0 as something no agent may do — correctly, because flipping a stored
`false` is the §9 breach. But *telling* the owner is not flipping it, and nothing
in the app had ever mentioned the switch the whole walk-away path waits on. When
a gate says "only the owner can do this", it is worth asking separately whether
the app can at least **ask** — the answer here was a whole feature.

---

## 2026-09-09 — Builder run (`claude/sweet-babbage-dto79f` → v0.403.0): the upload destination picker, plus a clean editor proxy-scaling sweep

**The run.** Baseline green before any change: **5,417 passed / 2 skipped**, full
suite headless, 28:13. One shipped item (v0.403.0, the bulk-upload destination
picker — full entry in [`SHIPPED.md`](SHIPPED.md)), verified in a real browser as
well as jsdom.

**Environment note, and it is the one AGENTS.md §7 already warns about.**
`scripts/agent-setup.sh` completed and the venv held nothing but `pip`
(`No module named pytest` from `.venv/bin/python`) — a PyPI read that timed out
mid-resolve. `pip install --timeout 120 --retries 5 -e ".[dev,web]"` fixed it in
one go, exactly as documented. Worth repeating only because the failure looks
like a broken checkout and is not.

**QA SWEEP — the A2 class (a pixel-unit editor parameter not scaled by the proxy
factor), across every op in `seestack/edit/ops/`: CLEAN.** The 2026-09-02
external audit's A2 was fixed "every named instance", which is a claim about the
instances it named, not about the class — so this enumerated every
`params.get(...)` in `tone.py`, `detail.py`, `background.py`, `geometry.py` and
`stars.py` and asked of each whether its unit is pixels and whether it passes
through `ctx.scaled_px` / `_scaled_box`. Every pixel-unit parameter does:
`detail.sharpen` `radius`, `detail.chroma_denoise` `radius`, `deconvolve`
`psf_sigma`, `background`'s two `box_size`s and `dilate_px`. The two that *look*
unscaled are not — `stars.reduce` and `stars.boost_nebula` hand their `size` to
`starmask.star_mask`, which divides by `ctx.proxy_scale` itself
(`starmask.py:56`), and `_reduce` additionally scales its own erosion footprint
(`ctx.scaled_px(size)`) rather than relying on the mask alone. The remaining
non-scaled numbers are genuinely unitless: σ thresholds, iteration counts,
fractional crop bounds, an angle. **No bug found; recorded here so the class is
not re-swept from scratch, and so the next run knows what "closed" rests on.**

**A test found a bug in the implementation before the implementation was
finished, which is the point of writing the awkward fixture.** The first
`Project.source_folders_under` returned the *first* path component under
`incoming/`, which is the obvious reading of "which folder did this come from" —
and `test_a_nested_container_target_is_not_offered_as_a_destination` failed,
because a whole-device drop (`incoming/MyWorks/M 31_sub/`) then reports
`MyWorks`, which is indistinguishable from a folder you could actually upload
into. It now reports the whole relative directory and the endpoint filters on the
separator. The lesson is the fixture, not the fix: the test was written for the
shape the owner's share actually has (§1 says his layout is the one to test), and
the single-folder fixture the code was written against could not have caught it.

**The browser found the other one, and code review could not have.** Every jsdom
assertion passed with `wrap="nowrap"` on the advice row — jsdom has no layout. At
420 px the real browser squeezed the fix button until its label read `Use “N`:
the one word the button exists to say, clipped. This is the same class as
v0.401.1 (a diagram whose geometry was right and whose meaning was unreadable),
two runs in a row. **Generalisation worth keeping: an assertion that an element
is in the document is not an assertion that it can be read.** Any run adding a
control beside text should photograph it at 420 px before believing the suite.

**First-run (`--empty`-shaped) probe: CLEAN, and the new control costs zero
height.** An app with no data at all, measured against the 2026-09-07 first-run
baseline in this file: `/` (Dashboard) **1,402 px phone / 1,028 px desktop** and
`/library` **1,252 / 923** — identical to the baseline in all four numbers,
with nothing overflowing and no console errors. The destination advice is the
sentence a beginner most needs on that screen and it self-hides until something
is typed, so the first-run Library is byte-for-byte the page it was. The empty
Library also gains a small honest improvement for free: the field's placeholder
is now `e.g. M 31_sub` rather than `e.g. M31`, which teaches the folder
convention at the moment it matters instead of modelling the near-miss.

**Playwright note, and the check that turned it into a non-finding.** The
playwright npm package installed on demand today expects
`chromium_headless_shell-1243` while the image ships `chromium-1194` /
`chromium_headless_shell-1194`, so a bare `chromium.launch()` dies with
"Executable doesn't exist … run npx playwright install" (which must not be run).
**`scripts/dogfood_probe.mjs` and `scripts/dogfood_editor.mjs` are already immune**
— both resolve `${PLAYWRIGHT_BROWSERS_PATH:-/opt/pw-browsers}/chromium` and pass
it as `executablePath` — so this cost nothing here and will cost nothing there.
It is recorded only for the *ad-hoc* case: a one-off browser script written in a
scratch dir (as this run's was) must pass `executablePath` itself, and the bare
launch is what fails.

---

## 2026-09-09 — Builder run (`claude/sweet-babbage-x2ai9f` → v0.402.0, v0.402.1): the phone-unreachable explanations, and a clean `--mosaic --editor` dogfood

**The run.** Baseline green before any change: **5,417 passed / 2 skipped**, full
suite headless, 26:37. Two shipped items, each with its own full Python suite
(5,417 / 2 both times), its own `vitest` (3,488 → 3,497 across 249 files) and its
own `vite build`; `tsc` clean throughout. `ruff` unchanged (446 pre-existing;
the only Python line this run touched is `__version__`).

**Both items are slices of one backlog entry** — *"a Tooltip is invisible on the
device the owner actually reads this app on"* — whose first two slices shipped as
v0.270.0 and v0.374.11. What made them worth a run rather than a tidy-up is that
the entry's own second slice had already turned out to be a **bug**, and so did
this run's second one.

**How the work was chosen.** The Bugs section holds no open, ungated bug; the
Ideas sections are mostly measured stand-downs (I extracted every top-level entry
across all six sections and filtered out the closed ones — ~55 remain, of which
most are explicitly real-data-gated, need owner sign-off, or carry a recorded
"probably not worth building"). The tooltip entry is one of the few with a
concrete, unbuilt, measurable "still open" line naming the editor.

**The measurement that scoped slice three.** Counting `<Tooltip` per route put
the editor at **24**, against Gallery 9 and Target 7 — and the ones that matter
are the eight-button row under the picture, four of which carried a real sentence
only on hover. The `FrameColumnGuide` idiom (v0.270.0) transfers to it exactly.

**The enumeration that found slice four, and it is the transferable part.**
While placing the guide I noticed the `Auto-crop edges` switch is a `<Tooltip>`
wrapped around a **control**, which is v0.374.11's defect one level up: there the
icon leaked its tap through to the control; here the tap *is* the control, and
there is no icon at all. That is a shape a grep can enumerate exhaustively — a
`Tooltip` whose first child is a `Switch`/`SegmentedControl`/input — and it found
**five sites, all of them live**: the editor's auto-crop switch, the Jobs notify
switch (whose tap also fires the browser permission prompt), and the Gallery's
three filters. **Generalises to:** when a fix lands on a *component*, ask what
the same mistake looks like one level up, at the call sites the component was
extracted from. A defect class rarely lives at only one altitude.

**Dogfood: CLEAN, and on a mosaic** (`scripts/agent-dogfood.sh --build --mosaic
--editor`, run against the v0.402.0 build). Nothing overflowing, no console
errors on either sample; the mosaic trim **7.9 %**, unchanged; the editor drive
clean on **both** the field and the mosaic run — all 21 ops re-rendered the live
preview, undo and redo applied. Page heights, phone: field editor **3,072 px**
(3,047 px before this run's guide line, +25 px), Target 3,078 px (unchanged),
`/life-list` 3,094 px; mosaic Target 3,407 px, mosaic editor 3,102 px. Desktop:
field editor 1,984 px, mosaic 2,113 px. **Re-probed after v0.402.1**
(`--build --no-stack`, which picks the newest target, i.e. the mosaic): the same
four numbers to the pixel — 3,407 / 3,102 / 2,113 / 2,104 — so the five hint
icons cost no height at all, including in the Gallery's wrapping filter row.
Still nothing overflowing, still no console errors.

**One process note on the two commits.** Both are frontend-only, and the second
was written before the first was committed, so the first commit's *full* Python
suite ran on a tree that also carried the second's non-`Editor.tsx` files. Rather
than claim "independently green" loosely, v0.402.0 was re-verified in a detached
worktree at its own commit: `tsc` clean, **248 files / 3,488 tests** green, and
the seven Python tests that actually read `frontend/` (the mirror tests,
`test_editor_op_placement.py` among them) **108 passed**. Cheaper than a second
25-minute suite for the same guarantee — but the ordering that made it necessary
is worth avoiding: commit the first slice before starting the second.

---

## 2026-09-09 — Builder run (`claude/sweet-babbage-7w0m19` → v0.401.0, `agent/dogfood-9w0m` → v0.401.1): the field-fill diagram, and the legibility bug only the browser had

**Dogfood pass: CLEAN on the field sample** (`scripts/agent-dogfood.sh --build`,
then again with `--no-stack` after the fix). Nothing overflowing, no console
errors, both times. Page heights on the sample-loaded app, phone: `/life-list`
3,094 px, Target 3,078 px (3,024 px unstacked), editor 3,047 px; desktop Target
2,057 px. The Target page is **+64 px** against the v0.338.1 baseline of 3,014 px
— that is this run's diagram, added *inside* the identity card rather than as
another banner, which is what the §1 standing IA rule asks for. No `--mosaic`
run: this run makes no Auto/editor claim, and the identity card's numbers are
catalogue-and-field arithmetic that a canvas shape cannot reach.

**The lesson worth keeping: a new *drawing* has a failure mode a new *string*
doesn't, and only a browser shows it.** `field_fill`'s overflow caption shipped as
*"Bigger than one frame — the outline shows how far it spills over the edges."*
Every test passed, the geometry was measured correct (the drawn ellipse is
`frac_long` × the drawn frame on each axis, verified off the screenshot's own
pixels), and the sentence is true. It is still **unreadable**, and the rendered
card is the only place that shows why: on the overflow branch there are suddenly
**two** shapes, the object covers the frame, and "the outline" names neither of
them. The reader cannot tell which shape is their field.

Two fixes, both invisible to a code read (v0.401.1): the ellipse is painted
**before** the frame, because SVG paints in document order and a dashed grey edge
under a translucent indigo wash reads as a smudge rather than as an edge; and the
caption names the frame — *"Bigger than one frame — it spills over the dashed edge
of your field."* Both are pinned (`test_field_fill_overflow_is_reported_not_clipped`
asserts the sentence says "dashed"/"your field"; the component test asserts the
`ellipse` precedes the `rect` in the DOM).

**Generalises to:** any future run adding a *picture* to a card. The tests can
only pin what you already know to look for, and "which of these two shapes am I
looking at?" is not a question that occurs to you while writing the shapes. Take
the screenshot.

---

## 2026-09-09 (Builder, branch `claude/sweet-babbage-8td9m9`) — two share-resolution items, one measured closure, and a clean `--mosaic` dogfood

**The run.** Baseline green before any change: **5,395 passed / 2 skipped**, full
suite headless, 26:57. Two shipped items (v0.400.0, v0.400.1), each committed
independently green with its own full-suite run — **5,399** then **5,403** passed,
2 skipped. Frontend green too (`tsc` clean, `vitest` 3,465 / 245 files,
`vite build` OK); `ruff` unchanged (the one pre-existing `I001` in
`routers/stack.py` was there before and is untouched).

**How the work was chosen, since this matters for the next Builder.** The Bugs
section holds no open, ungated bug, and the Ideas sections are mostly measured
stand-downs — I read every top-level entry in all six and came up with nine that
are not already closed, of which most are explicitly real-data-gated. What was
genuinely open and worth building was the **last "still open on size" item of the
2026-08-30 download-copy sweep** (the zoom clip), and that turned into two items
because building it required reading `_native_picture_source`'s gates, which is
where the second one was found.

**The second item is the more valuable of the two, and it was found by reading a
gate rather than by a test.** v0.384.0 shipped "the picture he shares of a
*Process target* run comes off the master instead of the 1024 px preview", and for
the owner's actual main path it did not, because **Auto trims the border** and any
recorded `preview_crop_json` was an outright decline. `auto_crop_border` is on by
default, so this was not an edge case — every share of every auto-edited picture
was still a re-encode of the 1024 px preview. The lesson worth carrying: a
decline list is written for the cases in front of the author, and its *reasons*
age at a different rate from its *entries*. This one's stated reason ("the render
is of the whole canvas") stopped being true for a display-space run the moment
v0.384.0 made that render go through the saved recipe — the same commit that made
the entry look correct is the one that made it wrong. **When a gate's docstring
gives a reason, re-check the reason and not just the condition.**

**A closure, measured rather than argued.** The 2026-08-30 idea *"a corner target
can't be centred in its own zoom clip"* proposed picking the **largest zoom in
[1.3×, 1.8×]** at which the focus can be the crop's true centre, for "a gentler
push-in that genuinely lands on it". Run against `crop_box_for_scale` itself, the
direction is backwards: centring needs `W/(2s) ≤ min(cx, W−cx)`, so the further
out the object the **more** zoom is required — today's 1.8× already lands exactly
on anything inside [0.278 W, 0.722 W], and the entry's own 0.96 W case needs
**12.5×**, an 80 px crop blown up to a 640 px frame. Entry cut to `SHIPPED.md`
with the table. It was filed as "size S; pure, engine-only, fully testable",
which is exactly the shape of entry a run picks up when it wants a quick win —
five minutes with the function it names saved that run.

**Live check: `scripts/agent-dogfood.sh --mosaic` — CLEAN.** Both samples loaded,
stacked and probed; **nothing overflowing, no console errors** at 1440 px and
420 px; mosaic trim **7.9 %** of the canvas (the §1 bug line is ~15 %). Tallest
page `[phone] /targets/Sample_M42_mosaic_2_2` at **3,407 px**. Then, because the
change is a *share*-path change and the probe never downloads anything, the app
was re-booted against the same scratch data and the endpoints were called
directly: on the mosaic run the share JPEG comes back **875×587** — the 907×615
canvas with Auto's trim reproduced, i.e. the v0.400.1 path live — and the zoom
clip **486×326**, which `…/zoom-clip/info` predicted **exactly**, on both targets.
That last agreement is the v0.400.0 anti-drift claim checked on real data rather
than on a fixture. (The bundled samples' canvases are *smaller* than the 1024 px
preview cap, so neither sample can show the size *gain* — that is what the
synthetic 1600 px fixtures in the two test files are for. Worth knowing before a
future run tries to measure a resolution claim on the sample and concludes
nothing changed.)

---

## 2026-09-09 (Scout, branch `claude/admiring-brahmagupta-idqivk`) — a clean dogfood, two rotation sweeps closed by tracing, one preview↔export non-finding measured, and one new beginner feature filed

**The run.** Baseline green before any change: **5,395 passed / 2 skipped**, full
suite headless, 22:59. Docs-only run — no product code touched, so no re-run
needed after (the two `docs/` edits below can't affect the suite). One new
beginner-feature idea filed to `IMPROVEMENTS.md → Features that serve real
workflows`; one already-CLOSED entry (v0.399.2) cut from the **Bugs** section,
whose full record already lives in `SHIPPED.md` and whose lesson is already in the
2026-09-09 block below — so the working list is left no longer than it was found
(§2 three-file rule), and the Bugs section is back to open bugs only.

**Dogfood: CLEAN** (`scripts/agent-dogfood.sh --mosaic --editor`).
- **Mosaic trim: Auto would cut 7.9 %** of the union canvas — the same figure
  v0.386.0/v0.391.1/the last three passes recorded, well under the ~15 % §1 calls a
  bug. v0.399.3/.4's trim fix has not drifted.
- **Page probes clean, both samples.** Nothing overflowing, no console errors.
  Tallest phone pages: field `/life-list` 3,094 px and `/targets/<field>` 3,078 px;
  mosaic `/targets/<mosaic>` 3,407 px, editor 2,917 px — all in line with the
  standing baselines, so no IA slice is indicated (fourth measurement agreeing).
- **Editor drive clean.** Field run: all **21** ops added one at a time, each
  re-rendering the live preview, then undo/redo — no console error, no failed
  request. Mosaic run: **20 of 21** ops driven identically clean (Stretch → Star
  reduction); the 21st (Boost nebula) was cut off by the run's own 900 s wall-clock
  `timeout`, not by any app error (the trailing "Target page has been closed" is the
  harness killing the browser). Effectively clean; budget >900 s for `--mosaic
  --editor` next time (the field + both probes + the field drive already eat most of
  it).

**QA rotation (AGENTS.md §1 / the four-item rotation) — where the yield was, and
where it was not.** The single-field engine core stays closed (do not re-sweep
`seestack/stack/*` / `seestack/calibrate/*` — twenty-plus clean sweeps). This run
worked the other three rotation items:

* **(3) Filesystem side effects of ASTAP / ffmpeg — traced CLEAN, and the §10
  guardrail is intact.** `seestack/solve/astap.py` never points ASTAP at the
  source: `_solve_once` copies the frame into a `TemporaryDirectory`, runs `-wcs`
  (never `-update`) there, reads the `.wcs`/`.ini` before the scratch dir is
  removed — so with `copy_to_cache` off, the owner's raw sub in `incoming/` is
  never written beside (ASTAP writes its sidecars next to the `-f` file, which is
  the scratch copy). `seestack/video/ffmpeg.py` reads the capture in place
  (`-i <path> -nostdin`) and pipes raw frames to stdout (`-`); it writes **no**
  output file and no sidecar. `ffprobe` is metadata-only. So neither binary can
  touch `incoming/`. (Traced by reading; a stub-binary run would add nothing — the
  argv and the scratch-copy discipline are the whole story.)
* **(1) Scale-dependent preview↔export parity — one op looked unscaled; measured,
  and it is a NON-finding.** Every user-facing pixel-radius op in `seestack/edit/ops/`
  is correctly shrunk by `ctx.scaled_px()` (star erosion, chroma denoise, sharpen,
  deconv, color-cal detection FWHM/aperture, bilateral spatial). The one exception
  is `tone.py::_scnr`'s internal `_SCNR_NOISE_SIGMA = 3.0`, the Gaussian that
  suppresses per-pixel chroma noise before the green-excess estimate — it is a
  *fixed* pixel sigma, not scaled. **Measured** (2400×2400 scene, green blobs at
  4/12/40/120 px widths, proxy step 8, `amount=0.8`): preview-minus-export green
  **mean +0.00001**, worst-case only **96.2 % of export's green removal** on the
  strongest-green pixels (a 3.8 % local under-removal), p99 |diff| 0.0042 on a
  0.10 sky. **And the obvious "fix" is wrong**: scaling the sigma to 3/8 px on the
  proxy would make it a near-delta, so per-pixel noise (preserved at full amplitude
  because the proxy is *strided*, not averaged) would no longer cancel — reintroducing
  exactly the magenta-sky bias this code was written to remove. The fixed sigma is
  correct for its noise-suppression job; the residual structure-removal divergence is
  immaterial. Recorded here so nobody re-scales it.
* **(2/4) Adjacent code read adversarially, all consistent** (not a full sweep of
  the routers, but read while chasing the above): `photometric.py` per-panel
  references on a mosaic (`_pointing_references` normalises each panel against
  itself, neutral fallback everywhere); `skyarea.py` union subtraction and block
  attribution; `calibration.py` unattended auto-bind gates (dark exposure gate
  applied *separately* from the gain/temp confidence distance — `_dark_match_confident`
  passes `exposure_s=None`, correct — plus dimension and bayer-conflict gates, and
  the "try every candidate in ascending distance, bind the first that clears a gate"
  loop that stops a top-ranked-but-unbindable master masking a bindable one);
  `stacktime.py` (new v0.399.0 — median seconds-per-sub over comparable runs, strict
  cost-class/canvas/min-frames gating, `None` on anything unproven); and
  `/stack-estimate` resolving `auto_reject` through the engine's own picker with the
  mosaic's per-pixel `depth` so the time estimate, the reach line and the resolved
  method all read the same decision. No bug found in any.

**The feature idea filed** (Features that serve real workflows): a *visual*
to-scale framing diagram — the object's angular extent drawn inside the S30 field
rectangle, *before* the shoot — as the picture-shaped complement to the existing
*textual* framing hint (v0.352.x). The ingredients already sit on the identify
response (`ObjectInfo.angular_size.size_arcmin` + the derived field the panel plan
is already computed against), so it is a pure `<svg>` in `ObjectInfoCard`, no new
endpoint, no network. Grep-checked against `IMPROVEMENTS.md`/`SHIPPED.md`: the
*textual* hint and the *post*-stack framing verdict exist; a *visual pre-capture*
one does not.

**Why no verified bug was filed.** Every subsystem read this run came back clean or
immaterial — consistent with the last several runs' "the app is genuinely
hardened" and "ready work is thin" conclusions. Per §2, the run did not manufacture
a bug or a marginal feature to have shipped something; it recorded the sweeps
(including the clean ones and the measured non-finding, so they aren't re-run),
filed one genuinely-novel beginner feature to keep the pipeline stocked, and
tidied one closed entry out of the Bugs section.

---

## 2026-09-09 (latest) — Builder run (branch `claude/sweet-babbage-u828ql`): D1's fourth instalment closed, and a clean `--mosaic --editor` dogfood pass on top of it

**The run.** Baseline green before any change (**5,389 passed / 2 skipped**, full
suite headless, 27:58). Final green on the branch: **5,395 passed / 2 skipped**,
26:11. Shipped **v0.399.3 + v0.399.4** — the fourth D1 instalment, filed the same
morning by the run before this one with five candidate fixes measured and
rejected. One backlog entry cut to `SHIPPED.md`; one short measured residual filed
in its place, so the working list is shorter than it was found.

**Why the sixth attempt worked where five levers had not.** The five rejected ones
were all *scalar* — move a fraction, move a ratio, compare two areas. The entry's
own closing note was that the failure is spatial, and that is where the answer
was: a reprojection ramp is **attached to the outline** and is a **band**, while a
thin panel is neither, and both of those are facts about the map rather than
thresholds over its depth histogram. The one number the rule does carry
(`FRINGE_OUTSIDE_FRAC`) is a loose pre-filter that the shape test stands behind,
not the discriminator — which is why it could be moved from 0.20 to 0.25 to clear
a fixture without moving the fix.

**A method note worth keeping: the fixture with the knife edge was the webapp's,
not the engine's.** At 0.20 the whole engine suite passed and six `test_editor.py`
tests failed, because `_ragged_border_coverage` ramps 1→2→3→4 against a panel
depth of **5**, so its outermost ring is *exactly* a fifth of a panel. On a real
Seestar panel of tens of subs the same ring is 3 %. The lesson is not "raise the
constant" — it is that a five-sub fixture cannot vouch for a fraction-of-a-panel
threshold at all, and the only reason this was caught is that the change was run
against the **webapp** suite and not only the module's own.

**Dogfood: CLEAN, and on the mosaic, which is what §1 asks for.**
`scripts/agent-dogfood.sh --mosaic --editor` on the fix:

- **`mosaic trim: Auto would cut 7.9% of the canvas`** — the *same* 7.9 % v0.386.0
  recorded before any of this, which is the result to want: the mosaic sample has a
  genuinely ragged union outline (4.8 % uncovered), so the honest trim is unchanged
  and the new rule only stands down where there is no border at all. Well under the
  "above ~15 % is a bug" bar.
- Editor driven on the **mosaic** run: all **21** ops the Add menu offers added one
  at a time, every one re-rendering the live preview, undo and redo applied, **no
  console errors and no failed requests**.
- Page probe on the mosaic target: nothing overflowing, tallest page
  `[phone] /targets/Sample_M42_mosaic_2_2` at **3,407 px**.

**What the run did not do: a second feature task.** The "Features that serve real
workflows" list was read end to end and every entry in it is shipped, closed,
declined, or gated on something an agent cannot supply; the top of "Autonomy &
friendliness" is the same. Rather than manufacture work (AGENTS.md §2), the run
went deep on the one priority-1 bug and stopped. Ready feature work for a Builder
is genuinely thin right now — that is a note for the **Scout**.

---

## 2026-09-09 (later) — Builder run (branch `claude/sweet-babbage-c9vw1a`): one shipped fix, one verified bug filed with five rejected fixes, and a lead whose own measurement was taken on the wrong map

**The run.** Baseline green before any change (**5,350 passed / 2 skipped**, full
suite headless, 27:16). Final suite green on the merged branch: **5,389 passed /
2 skipped**, 26:20. Shipped **v0.399.2** (a mosaic's thin panel is no longer faded
off the all-sky map, nor left out of the sky-area tally). Write-up in
[`SHIPPED.md`](SHIPPED.md). One verified priority-1 bug filed rather than fixed —
D1's fourth instalment, in "Bugs (fix these first)".

**Dogfood pass (§2), CLEAN — the fourth in a row.** `scripts/agent-dogfood.sh
--mosaic --editor`, both samples: **mosaic trim 7.9 %** of the canvas (the §1 bug
bar is ~15 %, and the same figure v0.391.1 recorded, so it has not drifted), all
21 ops added on the field **and** the mosaic run with the preview re-rendering
each time, undo/redo fine, nothing overflowing and no console errors at either
width. Tallest page, phone: **/life-list at 3,094 px**, in line with the v0.338.1
baseline — so no IA slice is indicated, for the third measurement running.

**The thing worth recording: re-measure a lead before you build from it, and
re-measure *what the code actually reads*.** The 2026-09-08 lead this run picked
up was filed as "cosmetic/display, low value — a fade on a map, not the picture
itself", with a measured `9.3 %`. Both halves were wrong, and each was wrong in a
way that only re-measuring could show.

* **The severity.** `stack_detail_mask` is not only the map's fade; it is also
  what `seestack.skyarea` counts. So the defect was also under-reporting the
  owner's *photographed sky* — a number on a page, not a shade on a picture.
  Nothing in the lead was untrue about the map; it had simply enumerated one
  consumer. **Grep the callers before accepting a filed severity.**
* **The measurement.** Its 9.3 % came from a **weighted** coverage map with 6 %
  per-pixel jitter. `stack_detail_mask` never reads that map — it loads the
  `_framecov.fits` *frame-count* sibling and falls back to the plain has-data
  footprint when there is none. On count maps the same shapes fade **nothing** at
  8-30 subs, and the real defect lives at wider depth spreads (5-60, 10-100,
  30-300), where 90 of 147 fully tiled rasters fade something and the worst loses
  26.3 % of its canvas. Building from the filed fixture would have produced a fix
  aimed at a shape the code never sees.

**Five fixes measured and rejected for the trim, which is why it is filed and not
shipped.** The same run reproduced a *second*, larger defect: `largest_covered_rect`
still crops a fully tiled mosaic by up to 19.8 %, on the on-by-default Auto crop.
Every scalar lever was measured and every one failed — lowering the level fraction
is **non-monotone** (0.08 → 11 bad, 0.04 → **13**, 0.03 → 2, 0.02 → 4, because a
lower reference raises the strict rectangle past the coverage bound and switches
v0.391.1's rescue *off*); reading frame counts instead of weights helps but leaves
14; tightening `TRIM_KEEP_RATIO` collides exactly (honest ragged 2x2 keeps 0.912,
broken 8x6 keeps 0.912); refusing to discard well-covered pixels collides in the
other direction (an axis-aligned rectangle over *any* irregular footprint cuts
good data, so the honest cases score 1.000); and "a fully covered canvas has no
border to trim" — the one guard that could only ever stop a crop — closes all 147
fixtures and fires on **0 of 147** once they are given an honest uncovered
outline. **A fix that works on every fixture and on no real canvas is a fix for
the fixture.** AGENTS.md §1 says not to blind-flip a constant on the on-by-default
hot path; with five levers measured, filing the numbers is worth more to the next
run than a sixth guess would be.

**A measurement trap that cost two sweeps.** `panel_coverage_level(covered,
min_frac=PANEL_LEVEL_MIN_FRAC)` binds its default **at def time**, so a harness
that rebinds the module constant to sweep the threshold silently measures the
*same* value every time. Two full sweeps came back reporting "0.05 and 0.04 are
identical to 0.08" before the flat rows gave it away. Monkeypatch the *function*,
not the constant — and treat a sweep whose rows are identical as a bug in the
sweep until proven otherwise.

---

## 2026-09-09 — Builder run (branch `claude/sweet-babbage-4yit4y`): a feature invented because the backlog was dry, a bug the *live check* found, and one filed perf idea closed by measuring it

**The run.** Baseline green before any change (**5,350 passed / 2 skipped**, full
suite headless, 28:47). Shipped **v0.399.0** (about how long this stack will take)
and **v0.399.1** (the Stack form named a method the run would not use, on a
mosaic), and closed the 2026-08-04 `/api/gallery/best` cache idea with the
measurement its own gate demanded. Write-ups in [`SHIPPED.md`](SHIPPED.md).

**The backlog really is dry, and this is the sixth run to say so** — "Bugs (fix
these first)" holds only entries gated on data no agent has or deliberate
stand-downs carrying their own numbers, and "Features that serve real workflows"
is entirely struck, closed or declined. The Ideas sections were swept
mechanically (split into top-level entries, filtered for those with no
SHIPPED/CLOSED/DECLINED marker) rather than read top-down; that took a minute and
is worth repeating.

**So the feature was invented, per the kickoff prompt's standing allocation, by
walking the journey rather than the list.** The Stack form's own panel already
answers *how big will this picture be* and *will it fit in memory*; the third
question a person has before pressing the button — **how long will this take?** —
had no answer anywhere in the app, while the Jobs page has been able to answer
the *running* version of it for months. That asymmetry is the kind of gap a
backlog does not contain.

**Two lessons worth carrying, both of them things a test said and I did not.**

**1. A new `stack_runs` column must NOT bump `SCHEMA_VERSION`.** The first
version of v0.399.0 did (22 → 23, with a migration step, the pattern most of that
table's columns still show), and `test_uncovered_fraction.py::
test_an_old_build_can_still_read_a_project_this_build_wrote` went red on
`PRAGMA user_version <= 22`. It is right: `Project._check_schema` **refuses** to
open a project stamped newer than the build, so a bump makes the feature
unrollbackable — upgrade-safe in one direction only. The column now reaches an
existing project through `_reconcile_table_columns` (it is in `SCHEMA_SQL`, and
that reconcile runs on *every* open, at the current version too), which is what
`uncovered_frac` and `targets.folder_name` already do. **If you are adding a
column to `frames` or `stack_runs`, do not write a migration step — add it to
`SCHEMA_SQL` and let the reconcile place it.** The red test was information about
the design, not an obstacle to it (the same lesson as 2026-09-08's rename).

**2. The live check found a bug the whole test suite could not.** v0.399.0 was
verified in a running app — boot `scripts/agent-dogfood.sh --serve --no-probe`,
stack the sample, read `/stack-estimate` back — and that put two numbers side by
side that no unit test had reason to compare: the endpoint said Auto would use
**sigma clipping**, and the run that had just finished had recorded **min/max**.
`auto_reject_resolved.method` re-derived the choice from the target's frame count
while the engine sizes it from the mosaic's panel depth. That is v0.399.1, and it
is the A6 class (v0.326.7) surviving in the *reporting* path a year after the
engine half was fixed. **The generalisable move: after shipping something that
reports what the engine will do, run it beside the engine actually doing it.**
The dogfood mosaic sample is enough — the field sample's 6 subs sit below the
estimate's own floor and would have shown nothing either way.

**A cheap measurement closed a filed perf item.** `GET /api/gallery/best` was
filed in 2026-08-04 as possibly "the most expensive read on the Dashboard", with
its own gate: *time it on a realistic library first*. Seeded 40 targets × 20 runs
and 80 × 40 straight into the DBs and timed it through a `TestClient`: **97 ms**
and **235 ms** — measured under a competing pytest run, so upper bounds, and the
same band as `/api/gallery` sitting beside it. Two orders off the 13.8 s
endpoints that justified v0.374.7–v0.374.9, so the staleness a cache would add to
the pinned-cover wall is not worth buying. Entry cut to
[`SHIPPED.md`](SHIPPED.md) with the numbers and the safe shape if it ever
reopens. **Seeding a library directly into the registry and project DBs costs
about two seconds and answers a "is this slow?" gate outright** — the same trick
the 2026-09-07 timing run used per-target.

**Dogfood: not a full §2 pass this run.** The app was booted and driven for the
live check above (field sample stacked, mosaic sample loaded and stacked, both
estimates read back), but no page probe or editor drive was run — three clean
`--mosaic --editor` passes are recorded within the last two days and neither of
this run's changes moves a page's layout beyond one dimmed line inside an
existing block.

---

## 2026-09-08 (later still) — Builder run (branch `claude/sweet-babbage-yzhopm`): three shipped items, and the one that had to argue with an existing test before it could exist

**The run.** Baseline green before any change (**5,337 passed / 2 skipped**, full
suite headless, 22:54). Final suite green on the merged branch: **5,350 passed / 2 skipped**, 22:08. Shipped **v0.397.0** (a mosaic is offered its object's
name), **v0.398.0** (a new beginner feature — "add tonight to calendar" on the
constellation nudge) and **v0.398.1** (the Lucky-imaging knob typed as a
percent). Write-ups in [`SHIPPED.md`](SHIPPED.md). No dogfood pass this run: three
clean `--mosaic --editor` passes were recorded in the last two days and none of
these three changes moves a page's layout, so a fourth would have been a
measurement of the same thing.

**The thing worth recording: a design that would have needed a good test
rewritten is a design worth changing.** The mosaic rename fix (v0.397.0) first
looked like "let `confident_object_title` accept an object whose extent contains
the centre". That version was written, and it turned two existing tests red —
both of them pinning that a point 0.5° from M 31 must be offered nothing. Those
tests are *right* about the danger (a wider radius claims neighbours) and merely
unlucky in their fixture (M 31's minor half-axis is 0.525°, so 0.5° really is
inside Andromeda). The temptation was to rewrite them onto a different object and
carry on.

Instead the design moved: the extent rule is now **only consulted when the cone
found nothing**, and **only for a mosaic-suffixed name**, behind a keyword that
defaults to today's behaviour. Both tests pass untouched, the caption path that
bakes names into shared pixels is provably unchanged, and the feature still does
the one thing it existed to do. **The red test was information about the design,
not an obstacle to it** — and the version that survives is strictly narrower and
easier to revert than the one that needed the test moved.

**And the gate the entry set was answerable after all, by enumeration rather than
by data.** The filed lead said the "inside its extent" rule needed *"a real
mosaic's centre offsets to validate before it decides a name; the synthetic
sample gives exactly one data point"*. That is the right worry for a *threshold*,
and this is not one — it is geometric containment — so the question it really
asks is "how often could two objects both claim a centre?". Running every one of
the 157 bundled objects against every other's centre answers it exactly:
**one** containment exists beyond the 0.25° cone (M 31 contains M 32, the
satellite galaxy that is genuinely inside it). A gate that reads as
"needs the owner's data" is sometimes a gate that needs *a measurement over the
data already in the repo*; it is worth asking which before deferring.

**A trap for the next run: `npx vite build` changes how the app 404s.** A test
asserting that an unknown `/api/...` path returns 404 passed alone and failed
after a frontend build, because `webapp/static/` then exists and the SPA
catch-all serves `index.html` with a **200** for anything unmatched. The
assertion was replaced with one against the app's own `/openapi.json` — which is
the honest question anyway ("is there an id-shaped variant of this route?") and
is independent of whether the frontend happens to be built in this container.

---

## 2026-09-08 (later again) — Builder run (branch `claude/sweet-babbage-e506ni`): the "use this name?" rename, a third clean dogfood pass, and one live check the tests could not have made

**The run.** *(Version chosen at merge time, per §11: this shipped as 0.395.0 until a concurrent Builder landed its own 0.395.0 — the auto-edit flip — mid-run, so it was re-bumped to **0.396.0** on the merge and both backlog/SHIPPED entries were kept as a union. Collision #15, and the rule worked exactly as written.)*

**The run.** Baseline green before any change (**5,312 passed / 2 skipped**, full
suite headless, 37:51). Shipped **v0.396.0** — the "this target is still named
after its folder — call it *Crescent Nebula*?" offer, the last open slice of the
Scout's 2026-08-27 #10 entry and the one that had been **🛑 BLOCKED** since
2026-09-01 on a real defect (a rename would have made the next scan allocate a
second folder). Write-up in [`SHIPPED.md`](SHIPPED.md).

**The blocked premise was true, and a test reproduced it before a line of the fix
existed.** `test_rename_survives_a_reopen_and_a_rescan_of_the_same_folder` was
written from the entry's own warning and failed on its first run with
`MyWorks_2026-08-14-6944ab3c` — i.e. the split library, exactly as predicted, in
under a second. Writing the test the *blocked* entry implied, before believing
the design, is what turned a "don't ship the chip on its own" into a shippable
feature: it named the missing piece (`targets.folder_name`, the alias row the
entry asked for) rather than leaving it to be reasoned about.

**Dogfood pass (§2), CLEAN — the third in a row.** `scripts/agent-dogfood.sh
--mosaic --editor`, both samples: **mosaic trim 7.9 %** of the canvas (the §1 bug
bar is ~15 %), all 21 ops added on both the field and the **mosaic** run with the
preview re-rendering each time, undo/redo fine, nothing overflowing and no console
errors on either width. Tallest page, phone: the mosaic Target page at **3,369 px**
(field sample 3,040 px), consistent with the v0.338.1 baseline; the feature this run
shipped adds nothing always-on (the offer is absent unless a target is folder-named
*and* solved onto an object), so the page heights it was measured against are its own.

**The part the suite could not have told me.** The card renders identically in
jsdom whatever order its lines are in, so the offer had landed *between* the two
italic "pure-wonder" lines the card deliberately keeps adjacent — the only action
on the card reading as a third fact. A screenshot at 1440 px and 420 px showed it
in one look, and it moved to the end (v0.396.0's last commit). The same live pass
also confirmed, on a real running app, what only integration can: one click
renames and the page heading changes, the offer withdraws itself, "Keep my name"
survives a reload, a rename onto a name another target owns comes back **400**
(hit by accident, which is the best way), and the **mosaic** sample — union centre
0.31° from M42 — is correctly offered nothing, because the offer is gated at the
0.25° title-grade cone. **Two of those five would have passed a green suite while
being wrong on screen.**

**Note for whoever reads `frontend/src/tiffDownload.ts` next:** the download-copy
sweep entry in `IMPROVEMENTS.md` still listed the colour-space axis as "still
open". It shipped; the line is struck. Grepping the shipped code before building
what an entry says is missing cost thirty seconds and saved a slot.

---

## 2026-09-08 (later still) — Builder run (branch `claude/sweet-babbage-9wjrt9`): the life-list share grid, a version collision with a concurrent run, and a second clean dogfood pass

**The run.** Baseline green before any change (**5,284 passed / 2 skipped**, full
suite headless, 28:54). Shipped **v0.394.0** — "My life list" as one shareable
picture (`seestack/lifelistcard.py`, `GET /api/life-list/grid.jpg`), the last open
slice of the 2026-08-27 life-list follow-ups; write-up in
[`SHIPPED.md`](SHIPPED.md). Then a §2 dogfood pass, recorded here because it found
nothing.

**Collision #14 — caught, and it cost nothing, because it was caught at the right
moment.** `origin/main` moved from `71c0419` to `359e6f5` *while the post-change
suite was running*, and the other run had shipped its own **v0.393.0**
(`batch_stack_tmp` skipped at scan time). Two different changes would have shared
one version number if the bump had been treated as settled at task start. §11's
rule did exactly what it exists for: the number was re-chosen **at merge time,
from the latest `main`** (0.393.0 → 0.394.0), and the `IMPROVEMENTS.md` /
`SHIPPED.md` conflicts were resolved as a **union** with both entries kept. The
full suite was then re-run on the merged tree (**5,312 passed / 2 skipped**,
28:43) rather than trusting the clean auto-merge — the other run had touched
`scanner.py` and `webapp/pipeline.py`. Nothing was lost either way; this is the
first collision in the diary where the two runs picked genuinely different items
and only the *version line* collided.

**Verified in a running app, not only in jsdom.** The new poster was fetched from
the live dogfood install (`GET /api/life-list/grid.jpg`, 200, 215 KB): M42 and M43
— both matched by the sample's own solved centre — carry the picture, the other
108 squares are drawn dim, and the strip reads *"My Messier list · 2 of 110
captured"*. The "Share my grid" button renders inside the existing header card at
1440 px **and** wraps cleanly at 420 px.

**Dogfood: CLEAN on all four probes** (`scripts/agent-dogfood.sh --mosaic --editor`,
then `--empty`), on a head ~80 versions past the last recorded pass:

- **Field sample** — nothing overflowing, no console errors. Tallest page
  `[phone] /life-list` at **3,094 px** (the Target page, the historic worst, is
  3,040 px).
- **Mosaic sample** — **Auto would trim 7.9 %** of the union canvas, comfortably
  under the ~15 % that §1 calls a bug (unchanged from the 2026-09-07 measurement,
  so v0.391.1's trim fix has not drifted). Nothing overflowing, no console errors.
  Tallest `[phone] /targets/<mosaic>` at 3,369 px.
- **Editor drive, both samples** — all **21** ops added one at a time, every one
  re-rendering the live preview with no console error and no failed request, then
  Undo and Redo. Clean on the field run *and* on the mosaic run.
- **First-run (`--empty`)** — nothing overflowing, no console errors. `/sky` again
  never reaches network-idle and is probed anyway (already recorded 2026-09-08,
  still not a defect). Tallest `[phone] /life-list` at 2,779 px.

**So the backlog is genuinely thin, and this run did not manufacture a third
task.** The "Bugs (fix these first)" section holds no startable entry: what is
left there is gated on data no agent has (a real cloudy night's subs, a real
solved frame with field rotation), deliberately stood down with the measurement
recorded, or filed-not-built with the reasoning attached — and the one entry a
run *could* have started, the `batch_stack_tmp` skip, was taken by the concurrent
run above. Two tasks, both finished, main left green.

---

## 2026-09-08 (later) — Builder run (branch `claude/sweet-babbage-lso4r6`): the editor's unsaved-changes guard, and a dogfood pass that finally ran the editor drive to the end on both samples

**The run.** Baseline green before any change (**5,284 passed / 2 skipped**, full
suite headless, 28:44). Shipped **v0.392.0** — the editor asks before it drops a
look you haven't saved; write-up in [`SHIPPED.md`](SHIPPED.md). Then a full §2
dogfood pass, recorded below because it found nothing.

**Dogfood: CLEAN on all four probes** (`scripts/agent-dogfood.sh --mosaic --editor`,
then `--empty`). This is the first pass in the record that runs every axis §1 asks
for — the field sample, the mosaic sample, the editor *driven to the end* on
both, and the first-run app — and none of them turned anything up.

**And it corrects the budgeting note the block below leaves.** That run measured
`--editor` at *~3.5 minutes per op* and truncated at 4 of 21, warning the next
agent to budget ≈2.5 hours for 21 ops × 2 samples. It does not cost that here:
the whole `--mosaic --editor` pass — booting, loading and stacking **both**
samples, two page probes and **both** full 21-op editor drives — took about **40
minutes** wall clock, i.e. roughly 30 s per op. So the earlier figure was that
container, not the flag. Run it in the background and poll the log; don't skip it
on the strength of that estimate.

- **Mosaic trim: Auto would cut 7.9 % of the canvas** — healthy (AGENTS.md §1: a
  trim above ~15 % is a bug, not a ragged edge). Unchanged from the v0.386.0
  measurement, i.e. v0.391.1's `TRIM_KEEP_RATIO` change left the honest case alone
  in a running app, not only in the unit fixtures.
- **Editor drive clean on both samples.** All **21** ops the Add menu offers added
  one at a time, live preview re-rendering on every one, then Undo and Redo — on
  the *field* run and again on the *mosaic* run. No console error, no failed
  request, either time.
- **Page heights, nothing overflowing, no console errors.** Field sample: phone
  Target **3,040 px** (the seventh consecutive measurement at 3,014–3,040 across
  ~180 versions), `/life-list` 3,008, editor 2,887, `/` 2,432. Mosaic sample:
  phone Target **3,369 px**, editor 2,917. **So the standing IA banner still says
  what it has said for three passes: do not open a speculative slice.**
- **First-run app (`--empty`) matches the 2026-09-07 baseline to the pixel** —
  `/life-list` 2,779 px phone / 1,224 desktop, `/` 1,402 / 1,028, `/library`
  1,252 / 923, `/combine` 1,196, `/settings` 1,067. Nothing overflowing, no
  console errors. (`/sky` again never reaches network-idle and is probed anyway,
  as before — the all-sky viewer holds an open request by design.)

**The pass also served as the real-browser check on this run's own change**, which
is why it was run after the commit rather than before: the probe walks *into and
out of* the editor page on both samples, and the editor drive leaves a 21-op
unsaved recipe on screen. Neither tripped the new guard — which is the design
working, not luck: the probe's editor opens on the v0.390.0 Auto seed, and
`committedKey` deliberately treats that seed as committed, so a page a beginner
merely *looked at* raises nothing.

**Backlog state — unchanged in shape, and this is now the fourth run to say so.**
"Bugs (fix these first)" holds no startable bug: every entry is either gated on
something an agent cannot supply (real elongated-target data, a GPU box, a legacy
library shape, a real cloudy night's subs), or a deliberate stand-down that
already carries its measurement. "Features that serve real workflows" is likewise
dry — every open bullet in it is struck, closed-as-already-built, or explicitly
declined. So one task shipped, and the run stopped rather than manufacturing a
second (AGENTS.md §2).

**One item re-examined and deliberately left filed, so it is not re-derived a
third time:** the LEAD about the all-sky "My map" fading whole thin panels
(`thumbnail.py` → bare `well_covered_mask`). The tempting fix is to port
v0.391.1's discriminator — compare against what the coverage *alone* allows and
halve the threshold when the depth rule does much worse. **It does not transfer,
and the filer was right.** v0.391.1 compares two *rectangles*, where a ragged rim
cannot form one; per-pixel, a real mosaic's fringe **is** covered, just thinly, so
a "kept ≥ 80 % of the covered area" rule would refuse to fade exactly the fringe
the map's fade exists for. A per-pixel fix genuinely needs the connected-region
discriminator the LEAD names, which is real engine work on a cosmetic navigation
aid. Left alone.

---

## 2026-09-08 (Builder, branch `claude/sweet-babbage-91fx05`) — dogfood CLEAN on both samples with `--editor --mosaic`; and the fixture inverted an engine measurement for the fourth time

**Dogfood record (CLEAN).** `scripts/agent-dogfood.sh --editor --mosaic`, run
because this run touched the editor and AGENTS.md §7 asks for both flags then.
Page probe: **nothing overflowing, no console errors**, tallest page still the
phone Target page at **3,040 px** (3,014 px at v0.338.1 — 26 px, i.e. noise, and
this run added no always-on surface). Mosaic trim: **Auto would cut 7.9 % of the
canvas**, unchanged from the v0.386.0 baseline and well under the ~15 % that
would be D1-shaped. Editor drive: **stopped after 4 of 21 ops** (Stretch, Curves,
Saturation, SCNR — each re-rendered the live preview with no console error and no
failed request), because it turns out to cost **~3.5 minutes per op** on this
container and the flag's own comment ("a few minutes") badly understates that:
21 ops × 2 samples is ≈ 2.5 hours, which does not fit inside a run that also owes
`main` a full suite. **Budget for that if you use `--editor`** — either run it as
the whole of a run's verification, or expect to truncate it. What the four ops
did establish is that nothing about the drive is broken and the preview loop is
healthy; the untouched 17 are covered by the 3,396-test frontend suite.

**End-to-end check of what this run shipped, on the running app** (worth
recording because the *silence* is the feature's designed default and is
indistinguishable from "it never runs"): `/identify` on the field sample returns
`nebula_class: "emission"`, the histogram endpoint carries the `colour_check`
key, and `measure_object_colour` on both real proxies returns `measured: True`
with `balance` **+0.004** (mosaic) and **−0.005** (field). Those land inside the
deliberate dead band, so the note correctly says nothing — the bundled samples'
stars are grey by construction, so there is no confident colour claim to make
about them. Anyone wanting to *see* the line rendered needs a picture with real
colour; the wiring is proved by the API probe plus the monkeypatched webapp
tests, not by the sample.

**The lesson worth keeping, and it is the fourth recording of it.** The
single-field photometric measurement (v0.389.1) came out at a consistent
**−9.7 % SNR** — a clean, reproducible, four-configuration result saying the pass
actively hurts — and it was **entirely the fixture**. Hazing a sub with
`sky + (pixel - sky) * factor` scales the sky *noise* by the factor too, because
noise rides on that same difference; every hazy sub came out proportionally
quieter, so after gain-matching all frames had identical signal *and* identical
noise and the correct `1/s²` combine weight became the wrong weight. Hazing the
**stars only** flipped the sign to **+0.16 … +3.33 %**, and the unweighted
extreme then landed within 0.1 % of the closed-form inverse-variance prediction —
which is what said the second fixture was the right one.

This file already records three of these (A1's scene, the 200-px sinusoid, and
the background-mesh floor's structured sky). What is new here is the *tell*: the
first result disagreed with a closed-form prediction and the run went looking for
why. **Work out what the answer should be before running the fixture.** A
measurement with no prediction to disagree with cannot catch its own fixture, and
a wrong fixture does not look wrong — it looks like a finding.
## 2026-09-08 (backlog-readiness run) — records moved out of the working list, verbatim (46 blocks: QA sweep records, dogfood baselines, process and collision notes, measured non-findings)

The three-file rule (AGENTS.md §2) puts these here. Each keeps the section it came from in its heading.
AGENTS.md §1's "search for DOGFOOD BASELINE" pointer now points at this file.

### Scout QA note 2026-08-26 (master-flat normalisation, drizzle neff) — from "Bugs"

- **⚪ Scout QA note (2026-08-26, traced — not filed; recorded so it isn't re-investigated):** also investigated the master-flat global-vs-per-channel normalization
  (`apply.py` ~205, `flat / np.nanmean(flat)`) and did **not** file it — the per-channel QE tint it leaves is
  a single per-channel scale that the downstream `post/color_cal.calibrate_color` white-balance fully absorbs,
  so it is not a real image-quality bug. The spatial (vignetting/dust) correction, the part that matters, is
  applied correctly. And the drizzle `_count`-as-`neff` per-channel over-count is negligible for normal RGB
  (needs per-channel NaNs, which co-debayered channels don't have).

### Scout 2026-08-13 minor / low-confidence notes — from "Bugs"

- **MINOR / low-confidence — NOT filed as verified bugs, recorded so they aren't re-investigated (Scout 2026-08-13):**
  - `seestack/render/thumbnail.py:837-838` — `_downsample_rgb` floors NaN to the frame's darkest finite value before
    box-averaging (unlike the main path's NaN-aware downscale), which would fill genuine coverage gaps with the
    darkest real value *and* darken pixels adjacent to a gap. **Not a live bug:** its only callers (`generate_thumbnail`,
    `render_sub_preview`) pass raw single subs with no NaN, so it's a no-op today. A **caution**: don't repurpose it
    for a mosaic/reprojected array without switching to the NaN-aware path.
  - `seestack/qc/runner.py:115-127` — with `auto_reject` **off**, an `auto:streak` frame is re-accepted on re-QC
    without re-checking `streak_detected`. Traced but **plausibly intended** (turning streak auto-reject off should
    undo its prior auto-rejections), so not filed as a bug; flagged only if the contract is meant to require the
    streak to be gone.
  - `webapp/watcher.py:81` (`self._stable &= seen`) — a one-poll transient `stat()` failure on an already-stable
    file drops it from `_stable`, re-arms it, and re-fires `on_batch_ready` a poll later. **Benign** — ingest dedup
    (`_dedup_key`) prevents any double DB row; cosmetic/perf only.
  - ~~**(Scout 2026-09-06) the one-click discover→build calibration path can build a contaminated master
    from a *mixed* folder.**~~ — **FIXED v0.369.1** (`masters.build_master(require_declared_kind=True)`,
    set only by `routers/calibration.build_master_from_incoming`). Full entry in [`SHIPPED.md`](SHIPPED.md).

### Scout adversarial QA sweep records, 2026-08-07 → 2026-08-13 — from "Bugs"

> **SCOUT ADVERSARIAL QA — stacking-engine + adjacent re-audit traced CLEAN; the two bugs above are in ingest /
> render, not the stacking math (Scout 2026-08-13, branch `claude/focused-keller-zi700s`).** Baseline: the
> stacking + calibrate subset is green (**845 passed / 2 skipped / 1801 deselected**, `-k "stack or accumul or
> align or mosaic or drizzle or calibrat or reject or weight"`) on a fresh `source scripts/agent-setup.sh`. Read
> adversarially, end to end (NaN/coverage semantics, rejection/weighting math, memory bounds, preview↔export
> parity): `accumulator.py` (all four accumulators; ±inf k-set identities; any-channel `_count`; Welford n<2→NaN),
> `stacker.py` (`_kappa_sigma_keep_mask`'s two keep-all widenings; photometric + weight application is identical
> across *both* κ-σ passes and the drizzle passes; `_resolve_auto_reject`), `align.py` (windowed reproject
> inset/valid; order-1 NaN-mask propagation `cval=1.0`), `mosaic.py` (wrap-safe circular mean at both outlier
> passes; pixel + megapixel caps), `drizzle_path.py` (`_clip_tolerance` float64 var, `neff`=true-frame-count gate,
> ULP(m²) resolution floor; half-open in-bounds), `weighting.py` / `photometric.py` (factor guards; `1/s²` fold),
> `reference.py`, `pointings.py`, `output.py` (already-display path; covered-only percentiles; channel order
> R/G/B write↔read), `calibrate/apply.py` (dark-vs-bias never-double-subtract; exposure-scale with both no-data
> masks restored). Also re-read `qc/grading.py` (reconsider fixed-point + cap determinism), `qc/noise_ratio.py`,
> and the planner pace math (`session_recap.recent_night_pace_s` vs frontend `clearNights.ts` — consistent, and
> guarded by v0.254.1's shared-constant test). No verified bug in any of these — consistent with the ~16 prior
> clean re-audits. The rotation's yield this run was in **ingest idempotency** and the **deepening reel**.

> **SCOUT ADVERSARIAL QA — stacking-engine re-audit at v0.270.2 traced CLEAN, this time backed by empirical
> probes; no verified bug found (Scout 2026-08-26, branch `claude/vigilant-knuth-q2sre0`).** Read adversarially
> end to end (NaN/coverage semantics, rejection & weighting math, memory bounds, preview↔export parity):
> `accumulator.py` (all four accumulators; ±inf k-set insertion for `MinMaxReject`; any-channel `_count`;
> Welford n<2→NaN), `stacker.py` (`_kappa_sigma_keep_mask`'s two keep-all widenings; photometric+weight applied
> identically across both κ-σ passes and drizzle; `_resolve_auto_reject`), `weighting.py` / `photometric.py`
> (factor guards; `1/s²` variance fold), `drizzle_path.py` (`_clip_tolerance` float64 var, `neff`=true-frame
> gate, ULP(m²) floor; half-open in-bounds), `mosaic.py` (wrap-safe circular mean both outlier passes; px+MP
> caps), `align.py` (windowed reproject inset/valid; order-1 NaN-mask `cval=1.0`), `output.py`
> (already-display path; covered-only percentiles), `calibrate/apply.py` (dark-vs-bias never-double-subtract;
> exposure-scale no-data masks), the **new v0.270.2** per-panel grading (`qc/grading.py` `_pointing_groups` +
> the per-panel *and* global reject rails) and its `stack/pointings.py::cluster_pointings` (union-find +
> dense relabel), and `render/thumbnail.py` (`autostretch` MTF + `_nan_aware_area_downscale_plane`).
> **New this run — empirical probes, not just reading** (reproduced tier): drove the pure functions directly and
> confirmed each behaves as designed — the σ=0 saturated-core keep (exact-equal kept; a would-be tiny-noise
> deviation can't arise because both κ-σ passes reproject the *same* deterministic pixels), `MinMaxReject` k=3
> tie-safety on an all-identical bright core, single-satellite k=1 drop, the any-channel `frame_coverage` guard
> under a per-channel NaN, and `_clip_tolerance` returning `+inf` on a bright-flat pixel (variance below
> ULP(m²)) vs a finite tol on a dim real-variance pixel. All correct. No verified bug — consistent with the
> ~17 prior clean re-audits. **Yield this run was in the backlog, not code:** traced the exact, correct
> implementation site for the front-of-queue `photometric_normalize`-on-mosaic item (engine `stacker.py:1312`,
> gated on `is_mosaic_canvas` mirroring the `final_gradient_removal or is_mosaic_canvas` precedent at
> `stacker.py:1735` — **not** `_stack_target`, which cannot know `is_mosaic` at option-build time), and added a
> new beginner feature to the Ideas list.

> **SCOUT ADVERSARIAL QA — stacking-engine core re-audit traced CLEAN; no verified bug found (Scout 2026-08-08,
> branch `claude/focused-keller-g87d0d`).** Baseline before the audit: the stacking + calibrate subset is green
> (**839 passed / 2 skipped / 1766 deselected** via the `-p no:pytest-qt` fallback, `-k "stack or accumul or align
> or mosaic or drizzle or calibrat or reject or weight"`, on a fresh `pip install -e ".[dev,web]"`). Read
> adversarially, end to end, tracing edge cases / NaN-coverage semantics / rejection & weighting math / memory
> bounds / preview↔export parity:
> - **`accumulator.py`** — all four accumulators (`WeightedSum`, `MinMaxReject`, `Welford`, and the windowed
>   variants). Checked: the any-channel `_count` frame-coverage (per-channel κ-σ can't under-count it); the
>   `±inf` k-set identities so an uncovered slot never wins an extreme, and the `inf−inf`-avoiding per-side sum
>   in `MinMaxReject.result`; Welford's `n<2 → NaN` variance being the *keep-single-coverage* signal for the
>   clip; NaN→missing everywhere. Holds.
> - **`stacker.py` run_stack** — the four dispatch arms (drizzle / min-max / κ-σ two-pass / single-pass mean) and
>   their shared setup. Verified photometric scaling is applied to the **same** pixels in *both* κ-σ passes (so the
>   clip reference and the clipped sum agree), the pass-1 vs pass-2 weight split (`weights` for the reference,
>   `combine_weights` = ×`1/s²` for the combine), the `n_used==0 and not cancel()` guards on every arm (no silent
>   all-NaN "success"), the `del wel` before pass 2 keeping peak ≤ the OOM guard's `_PEAK_CANVAS_ARRAYS`, and
>   `_kappa_sigma_keep_mask`'s two "no reference → keep-all" widenings (σ-unknown and mean-unknown) that stop the
>   clip turning real pass-2 data into a coverage hole.
> - **`align.py`** — windowed reproject inset/valid math, the `SUBPIXEL_SHIFT_CAP_PX` window-pad coupling, and the
>   order-1 NaN-mask propagation (`cval=1.0`, `>1e-6`) that marks a darkened boundary ring as uncovered rather than
>   letting it survive as a dimmed value.
> - **`drizzle_path.py`** — `_clip_tolerance` (float64 `E[x²]−E[x]²`, Bessel only on the *tol* not the floor test,
>   the ULP(m²) resolution floor, `neff` = true frame count not pixfrac-deflated weight), the `[-0.5, N-0.5]`
>   half-open in-bounds test, `intersects` vs used accounting, and `_compute_output_canvas` CRPIX/CD scaling.
> - **`weighting.py` / `photometric.py`** — geometric-mean factor guards (each factor's own `>0`/measurable gate),
>   the `1/s²` inverse-variance fold, the `<min_frames` neutral fallback and `[1/max_ratio, max_ratio]` clamp.
> - **`mosaic.py`** — wrap-safe `_circ_mean_ra_deg` / `unwrap_ra_deg` at both outlier passes, the MAD outlier gate
>   with its "never drop > half" backstop, and the pixel + megapixel canvas caps that fail fast with an actionable
>   error.
> - **`calibrate/apply.py` + `masters.py`** — the dark-vs-bias "never double-subtract" rule, exposure-scaling
>   `bias + (dark−bias)·ratio` with both no-data masks restored, the flat NaN(not-0) sentinel + `_FLAT_FLOOR`, and
>   `build_master`'s majority-shape reference + NaN-aware combine + `mad==0 → tol=0` (keep the spike out) clip.
> - **`bg/coverage_leveling.py` / `output.py`** — per-level detrend-before-threshold, the rescue/interp fill on the
>   *same fitted curve* clamped to the measured envelope, and the covered-only percentile / NaN-passthrough in the
>   TIFF/PNG writers. All consistent; this matches the documented ~16 prior clean audits. Rotation continues to the
>   webapp routers / watcher / ingest next run.

> **SCOUT ADVERSARIAL QA — the two owner-directed areas (AGENTS.md §1, 2026-08-07 self-expiring block) both traced
> CLEAN; no verified bug found in either (Scout 2026-08-07, branch `claude/focused-keller-r07kle`).** Baseline: the
> `-k video` suite is green (**118 passed / 2 skipped**) on a fresh `pip install -e ".[dev,web]"` with ffmpeg present.
> **(1) Moon/Sun lucky-imaging pipeline** — `seestack/video/{lucky,ffmpeg,framing,quality,discover}.py`, `webapp/video.py`
> and the `/api/videos*` router were read adversarially end to end. Traced: the two-pass grade→stack design's frame
> identity (grade keeps a scalar per frame, stack re-decodes the *same* frames and matches `keep_idx` by decode-order
> index); memory bounds (one frame materialised at a time in `iter_frames`; the accumulator holds a fixed handful of
> canvases regardless of length); decode edge cases (truncated tail frame dropped cleanly, missing `nb_frames`
> estimated from duration×fps, timeout/no-stream → clear `ValueError`); the alignment path (`phase_cross_correlation`
> shift, `_MAX_SHIFT_FRACTION` reject, `cval=np.nan` vacated edges → NaN-aware accumulator, reference = first kept
> frame so the *result* is fully covered by design); NaN/coverage semantics in `normalize_for_display` (NaN→black,
> percentile anchors on covered pixels only); the crop/uncrop artifact path (measured on the saved TIFF/PNG, sliced
> in each domain so nothing is re-quantised, full-frame backup written once and cleared on re-stack); and the
> keep-% advice math in `quality.py` (√score contrast, mean-not-median, monotone `_suggest`). **Empirically verified**
> the two-pass frame consistency (strides 1/2/3/5 each decode a deterministic, identical frame set on repeat calls)
> and ran a full 60-frame synthetic capture through `stack_video`→`normalize_for_display`→`measure_framing`→
> `sharpness_profile` (sensible n_kept/n_stacked, 0 NaN by design, worthwhile crop found, coherent advice sentence).
> **(2) Mosaic panel-alignment / seam path** — `seestack/stack/mosaic.py` (wrap-safe `_circ_mean_ra_deg` /
> footprint-outlier rejection, the iterative canvas-fit with pixel + megapixel memory caps that fail fast with an
> actionable error), `seestack/stack/photometric.py` (per-frame multiplicative scale, neutral fallback, bounded
> clip, orthogonal to quality weighting), and `seestack/bg/coverage_leveling.py` (`level_by_coverage` and the
> v0.233.0+ `measure_seam_residual` diagnostic). These are mature (≈16 prior clean audits; the v0.232.x
> object-mask-starvation fixes are in and tested) and the seam-residual is a best-effort try/except *diagnostic*
> that cannot corrupt the image. Nothing new found. **Both areas passed a real pass (not a skim), so the
> self-expiring directive block has been removed from `AGENTS.md` this run and the rotation returns to normal.**

### Scout / Builder audit and re-audit records, 2026-07-14 → 2026-07-26 — from "Bugs"

> **Deep plate-solve + ingest-heal integration audit — the faint-field solve root cause MEASURED with the real ASTAP CLI +
> the bundled d05 database; the owner's re-scan heal verified SAFE end-to-end; four new verified bugs filed and measured
> ground truth added to the queued solve ideas (Audit 2026-07-24, branch `claude/astrostack-plate-solve-audit-u4wjk1`).**
> Baseline suite green (**1996 passed, 2 skipped**). This run attacked the #1 unresolved owner pain — ASTAP failing on
> faint/sparse fields so auto-stacks stay thin — *empirically*: downloaded the exact ASTAP CLI (2026.07.16) + d05 star
> database the Docker image bundles and measured the app's real ladder (`astap.py::_SOLVE_LADDER`) on realistic synthetic
> Seestar OSC subs (1080×1920 RGGB, sky 1200 ADU, σ≈45, FWHM 2.1 px, 25 stars, CFA-weighted fluxes; ASTAP's own solve logs
> parsed for per-rung star-detection counts — detection precedes catalog matching, so synthetic frames measure it exactly).
> **Headline results (reproduced; numbers in the ⭐⭐ thin-stack entry's new ▶ block below):** (1) the ladder's escalation
> direction is *backwards* for faint Seestar frames — ASTAP already auto-picks bin 1×1 on the default first rung for a
> 1080×1920 frame, and the bin-2/bin-4 rungs strictly *lose* detected stars at every faintness (22.3 → 16.8 → 5.0 of 25 on
> bright frames; 5.0 → 1.0 → 0.0 on faint; bin 4 finds ~nothing even on bright frames); (2) the ladder's hot-pixel
> rationale is empirically void on this ASTAP version — 200 planted hot pixels changed bin-1 detection not at all
> (13.8 → 13.8, 7.8 → 7.8 stars); (3) the queued **stack-then-solve bootstrap idea WORKS**: at a faintness where a single
> sub detects 0–2 stars (below ASTAP's ≥3-star abort), a plain mean of 8–16 subs detects 6–12 — solvable — and is robust
> to ±2 px uncompensated inter-sub drift; (4) measured **non-levers** (so no future run burns time on them): a deeper star
> database (decoded d05's area files: GAIA DR3, density-capped ~500 stars/deg²; census over all 1476 sky areas = min 124 /
> median ~490 catalog stars per Seestar FOV — the catalog always outguns a 10 s sub's detection), the unused `-check` /
> `-m 1` / `-speed slow` ASTAP flags (zero detection change on faint frames), and radius/timeout tuning (a *failed* search
> costs only ~4 s at the 30° default radius, 0.2 s at 5°). Also verified: the webapp Settings' ASTAP FOV/timeout never
> reach real solves at all (new ⭐ bug below). **Ingest-heal verdict (the owner's imminent redeploy): SAFE** — on a full
> synthetic reproduction of the polluted install (bare-output target + merged subs + `_mosaic` pair + `_video` +
> duplicates), the pre-heal wrong result was reproduced with the real stacker (7 frames, the low-res on-device output as
> reference, `is_mosaic` flipped, padded 323×483 canvas), ONE re-scan heals it (output frame → `auto:seestar_output`,
> excluded from both the stack and reference pools; post-heal n_used=6, native 320×480 canvas, `is_mosaic=False`), a
> second re-scan is byte-identical (idempotent), a user re-accept survives later scans, nothing is ever deleted
> (sha256-verified), and the `<T>_sub` duplicate-target cleanup flags exactly the junk targets and only them. Three real
> edge defects filed below (mixed-library mass-reject; legacy whole-device-drop target never healed; cleanup discards user
> history) — none on the owner's specific path. **Scope note:** the end-to-end image-quality sweep planned for this run
> was interrupted (its subagent hit the session usage limit mid-run); its preview-aliasing thread was completed by hand
> and filed below (stride-decimated adjustable render), and partial evidence for a hot-pixel-on-thin-min-max-stacks
> thread sits in that session's scratchpad — the colour/stretch/gradient/denoise auto-path quality sweep remains the top
> re-audit candidate for the next Scout run.

> **Integration audit — Seestar data-shapes + output-resolution + thin-stack verification; THREE NEW verified
> (reproduced) ingest-family bugs filed; the three queued owner fixes verified, with one significant completeness gap
> (Audit 2026-07-24, branch `claude/astrostack-integration-audit-43giya`).** Baseline suite green (**1858 passed,
> 2 skipped**). This run deliberately audited the *integration / real-data-shape* seams the hourly unit-test-driven
> agents don't exercise — the Seestar folder convention end-to-end (fresh vs upgraded-in-place library, nested
> layouts, non-Latin names), the output-resolution path, and the auto-stack frame accounting — rather than re-treading
> the repeatedly-clean stack math. **Verdicts on the three queued owner fixes:** (1) **Seestar folder convention
> v0.184.9 — CORRECT for a fresh library** (map `_sub`/`_mosaic_sub`, skip bare-output-with-sibling and `*_video`,
> case-insensitivity all re-verified by running the classifier and full scans) **but INCOMPLETE in three ways**:
> (a) the ⭐⭐ upgrade-path pollution bug filed below — on the owner's own already-polluted install, a re-scan merges
> the raw subs INTO the old bare-output target, so the Seestar's on-device stacked output keeps stacking into the
> final image and is *preferentially picked as the stack reference* (reproduced end-to-end); (b) the already-filed
> mosaic bare-output gap re-verified still present (`[('M31', 1 output file), ('M31_mosaic_sub', 2)]` →
> spurious 1-frame `M31` target); (c) the container-nesting bug filed below (a wholesale `MyWorks/` drop merges every
> target+output+video into ONE target — the convention only fires at depth 1 while `find_fits_files` is recursive).
> (2) **Low-resolution output — VERIFIED at HEAD for every engine artifact**: the default (non-drizzle) canvas equals
> the native sub (`run_stack` `dst_shape=ref_shape` unless a genuine mosaic; Builder's 480×320 repro re-confirmed);
> the memory guard **refuses** with an actionable `MemoryError` and never silently shrinks a drizzle canvas
> (`_guard_stack_memory` — `_largest_drizzle_scale_within_budget` is used only to word the suggestion); and
> FITS/TIFF/full-res-PNG are written unscaled (`output.py` — only the 1024 px preview PNG and 2048 px share JPEG
> downscale, by design). The one *surviving* low-res-adjacent mechanism on real data is the upgrade-path pollution
> below: a lower-res on-device output captured as reference flips `compute_mosaic_canvas`'s `is_mosaic` heuristic
> (it compares union-vs-reference **pixel** areas across **different pixel scales**, `mosaic.py:330`) so a plain
> dithered single-field target stacks as a padded "mosaic". (3) **Thin-stack gibberish — the shipped halves are
> CORRECT**: `auto_stack_min_frames` (default 3) holds a thin target in `_pipeline_body` *without* marking the
> attempt marker (so it re-checks next scan), only the hands-off scan is gated (interactive paths deliberately
> unaffected), and the `used = accepted − unsolved` accounting is consistent; the remaining root stays faint-field
> plate-solve success — the ASTAP ladder (`astap.py::_SOLVE_LADDER`) only escalates *noise suppression* (bin 2×/4×,
> star cap), so the queued sensitivity-side ideas (relaxed-parameter retry, stack-then-solve bootstrap) are the right
> attack; hint threading and the fatal-setup-error short-circuit re-verified sound.
>
> **Re-audit — stacking-engine core CLEAN again; shipped one verified reproduced solve-path state-corruption bug;
> filed two more verified bugs (Scout 2026-07-24, branch `claude/kind-mccarthy-hntcnk`).** Baseline suite green
> (**1857 passed, 2 skipped**). Three independent adversarial audit sub-agents (each told to skip the
> repeatedly-confirmed-clean items and hunt only for *new* defects) plus my own traces re-covered: (a) **stacking hot
> path** — `accumulator.py` (MinMaxReject band partitions + denominators brute-forced against a NumPy reference over
> 200 random N≤7/k≤3/NaN configs; ±inf-seed `_mins.sum()+_maxs.sum()` indexed per-side so no inf−inf; Welford
> mean/var vs `np.nanmean`/`np.nanvar(ddof=1)` incl. n<2→NaN, stable at 1e6-mean unit-delta; WeightedSum
> sum/weight + coverage), `stacker.py` (κ-σ keep-mask both NaN-widen guards, `_auto_kappa_min_frames` n=11@κ=3,
> dispatch gates min_max n≥3 / sigma n≥4, memory-guard `2+2k` charge consistent with `estimate_stack`),
> `drizzle_path.py` (CRPIX `(c−0.5)·s+0.5` / CDELT `/s` round-tripped vs astropy at scale 1–3, `_clip_tolerance`
> neff/var-floor float64, half-open pixmap bounds), `weighting.py`/`photometric.py` (all five factors bounded
> [0.1,1] with correct penalty direction, geo-mean in-range, inverse-variance `/s²` fold + hazy→scale-up direction)
> — **CLEAN**; (b) **render / output / router surface** — `render/thumbnail.py` (STF/asinh NaN masks, 99.5-pct
> ceiling, NaN-preserving stride), `stack/output.py` (covered-pixel percentiles, NaN→0 only at final encode,
> `_sanitize_basename` traversal guard), and the seven read routers (server-side `safe`/master-id resolution, no
> client filesystem paths, clamped pagination, per-target failure isolation, stable response models) — **CLEAN**;
> (c) **ingest / watcher / QC** — `StabilityTracker` debounce + re-arm, stranded-batch single-retry bound, ingest
> realpath dedup + fingerprint content-swap recovery (mtime stored REAL, exact round-trip), QC modified-z/meanAD
> fallback + practical-significance floors + reject cap, `median_eccentricity`/`median_star_flux` empty-list guards,
> `green_channel` no 16-bit overflow, streak determinism/div-by-zero guard, ASTAP solve ladder raise-on-total-failure
> — **CLEAN**. **Three NEW verified bugs this run:** (1) **SHIPPED (v0.184.14, struck below)** — the plate-solve
> `solved-but-unreadable-WCS` branch clobbered a frame's `qc_error`/`qc_error_final` reject reason (reproduced,
> fail-before/pass-after regression-tested); (2) **FILED (open, ⭐ below)** — an in-place auto-edit (`Process target`
> / `auto_edit_on_autostack`) rewrites the preview PNG but never marks the run display-space, so the History
> one-sub-vs-stack reveal / stretch-suggestion / Adjust diverge from the clicked thumbnail (traced; broken-UX parity,
> Builder — needs a design decision on stamp-vs-record); (3) **FILED (open, below)** — the Seestar-aware scanner
> skips a bare `<T>/` output folder only when a `<T>_sub` sibling exists, not a `<T>_mosaic_sub` sibling, so a
> mosaic's bare on-device output can still become a spurious 1-frame target (traced; device-naming-dependent). Two
> ideas filed below (stacking-progress ETA; "Try it with a sample image" onboarding).
>
> **Re-audit — stacking engine + render/output-parity + calibration/weighting + ingest/watcher/auto-stack orchestration
> ALL CLEAN again; NO new verified bugs this run (Scout 2026-07-24, branch `claude/kind-mccarthy-n1kcnj`).** Baseline
> suite green (**1839 passed, 2 skipped**). Three independent adversarial audit sub-agents (each told to skip the
> repeatedly-confirmed-clean items and hunt only for *new* defects) plus my own end-to-end reads re-covered: (a)
> **stacking geometry / mosaic / drizzle** — `mosaic.py` (RA-wrap 0/360 straddle at high dec via `unwrap_ra_deg`/
> `_circ_mean_ra_deg` → 0.57° span not a bogus ~360°; single/zero-frame groups; CRPIX 1px-pad; canvas caps never a
> zero-size axis), `drizzle_path.py` (super-res canvas re-derived exact on a **30°-rotated CD-matrix** reference at
> scale 1.0/1.5/2.0 — input (10,20)→`scale·(p+0.5)−0.5` in every case; `has_cd()` CD-scaling; half-open pixmap bounds),
> `reference.py`/`pointings.py`, and an **end-to-end two-panel mosaic reproject** with **zero interior holes and zero
> empty rows/cols** inside the covered bbox — **CLEAN**; (b) **render / output / preview↔export parity** —
> `render/thumbnail.py` (STF/asinh NaN-aware, robust 99.5th-pct high-end, NaN→0 only at final encode), `stack/output.py`
> (FITS/TIFF/full-res PNG never downscaled; percentiles over covered pixels only), and a **per-op proxy-vs-downscaled-
> export parity reproduction** (proxy_scale=4: RMSE ≈0 for tone/background/stars/sharpen; the only larger deviations —
> `denoise:bilateral` 0.018, `deconvolve` 0.019 — are the already-captioned sub-pixel-on-decimated-grid limits, not
> defects) plus a **negative-outlier stretch-robustness reproduction** (a −40000 hot pixel gives **0.0% faint-detail
> contrast loss** because STF/asinh re-anchor to robust per-channel median/MAD after the affine normalize) — **CLEAN**;
> (c) **calibration + weighting** — `apply.py` (dark-then-flat raw-Bayer order; exposure-scaled dark gated on `>0` for
> both 0/negative EXPTIME cases — reproduced; `_FLAT_FLOOR` floors negative/NaN/inf flat pixels to 1.0 — reproduced;
> float32 exact for Seestar 16-bit), `masters.py` (all-NaN→NaN, MAD=0→median, atomic write), `weighting.py`/
> `photometric.py` (every weight provably in [0.1,1], can't reach 0; inverse-variance fold direction verified
> hazy→scale-up→down-weight; photometric normalizes to the **median** so an anomalous reference can't skew it), and
> `webapp/calibration.py` auto-bind (standalone-bias skipped when a dark is bound → no double-subtract; dims-gate blocks
> a wrong-size master) — full calibrate suite **82 passed** — **CLEAN**. My own reads of **`io/ingest.py`** (realpath
> dedup, size+mtime fingerprint content-swap recovery, truncated-cache refresh + stale-WCS reset), **`webapp/watcher.py`**
> (`StabilityTracker` quiet-period debounce, stranded-batch re-arm, `pending = accepted is False` hand-off contract) and
> **`webapp/pipeline.py`** auto-stack orchestration (`_auto_stack_frame_count` frame-count+`prior_max`+attempt-marker
> guard; per-target try/except isolating a mid-scan DELETE/DB-lock; min-frames hold + mixed-pointing skip **without**
> marking the attempt so the next scan re-checks) agreed — **CLEAN**. **No bug rose above the noise floor, so per
> AGENTS.md §2 nothing was manufactured.** Three verified *non-impacting* observations were examined and NOT filed as
> bugs (recorded here for provenance): (1) `wcs_io.py::footprint_radec_deg` sizes each frame footprint from pixel
> *centres* `(0…w−1)` not the true `(−0.5…w−0.5)` extent (undersizes ~½px/edge) — harmless because the reproject valid
> region is further inset by `FRAME_EDGE_INSET_PX=3` and the canvas carries a 1px pad, so coverage always lands strictly
> inside; (2) `_compute_output_canvas` copies SIP coefficients unscaled onto a finer drizzle grid — self-consistent (all
> frames map through the same `out_wcs`) and moot since Seestar/ASTAP WCS is plain TAN+CDELT/CD; (3) the unattended
> auto-bind confidence gate (`_match_distance ≤ 1.0`) accepts a dark at up to a 2× gain or 10 °C temp mismatch —
> degrades to residual over/under-subtraction (never NaN/inf), and moot for the fixed-gain Seestar target user. One
> autonomy improvement idea (auto-restack an uncalibrated target once confident masters become available) and one new
> beginner feature ("Add darks in 3 steps") filed below.
>
> **Re-audit — full stacking-engine + calibration + webapp-orchestration sweep CLEAN again; NO new verified bugs this
> run (Scout 2026-07-24, branch `claude/kind-mccarthy-cj5313`).** Baseline suite green (**1840 passed, 2 skipped**).
> Three independent adversarial audit sub-agents (each told to skip the previously-confirmed-clean items and hunt only
> for *new* defects) plus my own end-to-end reads re-covered: (a) **`align.py` + the whole per-frame path** it drives —
> `bg/per_frame.py` (all-NaN/negative-sky/degenerate-field background degrade-safely; the `_EXCLUDE_PERCENTILE_LADDER`
> falls all the way to no-subtraction with a warning, never a partial colour-cast), `bg/hot_pixels.py`,
> `io/fits_loader.py` (`bilinear_debayer` zero-sample sentinel `plane != 0` **verified benign by repro** — a genuine
> zero sample is preserved in every channel; integer-mosaic upcast before neighbour sums, odd-dim edge-pad cropped back
> inside the 3px align inset), `calibrate/apply.py`, `wcs_io.py`, `core/xp.py` — and confirmed the subpixel-refine cap
> (`|dy|>CAP or |dx|>CAP`) does **not** catch a NaN shift but is **unreachable** (patches are NaN-filled to finite before
> `phase_cross_correlation`, and finite inputs never return NaN; the spurious `(-0.7,-0.7)` on a featureless overlap
> shifts ≤5px, exactly consumed by the `pad=SUBPIXEL_SHIFT_CAP_PX=5` window) — **CLEAN**; (b) **`weighting.py` /
> `photometric.py` / `reference.py`** — every weight reaching the accumulator is provably in (0,1] (each factor
> `clip([0.1,1])`, geo-mean stays in-range; single-frame / identical-frame / zero-star / all-None-metrics / tiny-
> transparency all give finite weights, verified by running `compute_frame_weights`), NaN can't reach it (sqlite coerces
> NaN→NULL, dropped by the `is not None`+`>0` guards; QC never emits inf), photometric normalizes to the *median* (no
> degenerate-reference case) with scales clipped `[1/max_ratio, max_ratio]`, reference tie-breaks deterministic
> (`min(range, key=score)` over `ORDER BY id`) — **CLEAN**; (c) **the webapp autonomy path** — `pipeline.py`/`jobs.py`/
> `calibration.py` (auto-calibrate master selection: `_dims_ok`/exposure/gain/temp gates use the *same* raw dims the
> engine's `CalibrationMasters.validate` hard-fails on, so a bound master always validates — no wrong/mismatched master
> silently applied; no-match → uncalibrated, never corrupt; the standalone-bias block correctly skipped when a dark is
> bound — no double-subtract; `run_stack` **raises** on every degenerate path so a failed auto-stack can never publish a
> black "success"; all four per-target loops isolate a mid-run DELETE / DB-lock; no changed default on live upgrade —
> `auto_stack`/`auto_edit_on_autostack`/`auto_bind_calibration`/`mixed_pointing_guard`/`auto_grade_frames` all default
> `False`) — full webapp suite **661 passed** — **CLEAN**. My own reads of **`output.py`** (preview/full-res-PNG/share-
> JPEG only ever downscale, NaN→0 only *after* covered-percentile stats), **`calibrate/masters.py`** (`_sigma_clip_mean`
> MAD=0→median-degrade, NaN-aware combine, atomic master write) and the **`estimate_stack`/drizzle-scale-budget** path
> (`suggested_drizzle_scale`/`suggested_reference_canvas` charge the same planes the run-time guard does; `run_stack`
> honours the requested scale or *refuses* via the guard — it never silently shrinks output) agreed — **CLEAN**. **No
> bug rose above the noise floor, so per AGENTS.md nothing was manufactured.** Two *latent-but-unreachable* defensive-
> hardening notes (not bugs — they cannot fire on real data) recorded in the Minor group below; one autonomy idea
> (WCS-free star-registration fallback for faint fields — a direct attack on the ⭐⭐ thin-stack root) and one new
> beginner feature ("Point here tonight") filed below.
>
> **Re-audit — full stacking-engine sweep CLEAN again; shipped one verified memory-estimate/guard broken-UX bug
> (Scout 2026-07-24, branch `claude/kind-mccarthy-8fwg93`).** Baseline suite green (**1826 passed, 2 skipped**).
> Three independent adversarial audit sub-agents plus my own reads re-covered the engine end-to-end and all came back
> matching the repeatedly-clean documented state: (a) **accumulator + drizzle reductions** — `accumulator.py`
> (MinMaxReject band partition `lt3=[1,2]`/`single=[3,2k]`/`full=[2k+1,∞)` gapless with every denominator provably ≥1,
> ±inf seeds never leaking into a sum, Welford `add`≡`add_window` no read-before-write aliasing, WeightedSum
> gap→NaN/single-covered kept), `drizzle_path.py` (`_clip_tolerance` neff gate at the true frame count, `result()`
> returns the running weighted average with no re-divide, half-open pixmap bounds, CRPIX/CDELT super-res scaling) —
> **CLEAN**; (b) **align + stacker orchestration** — per-frame calibration exposure threading verified correct (each
> frame's own `info.exposure_s` from its own header → a fresh `bias+(dark−bias)·ratio` array per call, no stale/shared
> value; concurrent workers safe on read-only masters), κ-σ two-pass keep-mask NaN widenings, subpixel-shift NaN
> re-mask, CPU cval=NaN ↔ GPU cval=0 parity via `inset≥1`, the min/max-reject memory-guard plane charge
> (`2+2k` exactly matches the accumulator's persistent planes), cancel paths (→`StackResult(cancelled=True)`, never
> raise), and frame accounting — **CLEAN**; (c) **calibrate + mosaic** — `apply.py` dark-then-flat raw-Bayer order,
> dark-scaling direction/ratio (`t_light/t_dark`) and its zero/None-exposure guards, bias never double-subtracted,
> `_FLAT_FLOOR` divide guard, `masters.py` all-NaN→NaN / MAD=0→median, `mosaic.py` RA-wrap 0/360 + pole seams and the
> canvas caps never yielding a zero-size axis — **CLEAN**. **One NEW verified bug found + fixed + shipped this run**
> (struck below, **v0.184.10**): `estimate_stack`'s reference-canvas suggestion computed its `ref_peak` **without** the
> `min/max-reject` canvas-plane charge that both the main peak estimate and the run-time OOM guard apply, so a
> mosaic-union run with `min_max_reject` on and `min_max_reject_count ≥ 2` could offer a one-click "use the reference
> canvas instead" that the guard would then refuse with `MemoryError` — reproduced + regression-tested. Two speculative
> observations examined and NOT filed (both non-corrupting, already in the documented-benign family): the drizzle
> `clip_reference` per-channel `neff` any-channel-OR (marginal ~13% tolerance tightening, needs astrophysically-rare
> per-channel-differing NaN masks); and a frame with a missing/zero `EXPTIME` silently taking the unscaled dark while
> the exposure-mismatch advisory is suppressed (documented conservative fallback = scaling-off behaviour; Seestar
> always writes EXPTIME). One improvement idea + one new beginner feature filed below.
>
> **Re-audit — stacking engine core CLEAN again; TWO NEW verified bugs found in the solve/QC/ingest + auto-stack
> orchestration paths; shipped one, filed the other (Scout 2026-07-23, branch `claude/kind-mccarthy-nt4l9m`).**
> Baseline suite green (**1825 passed, 2 skipped**). Three independent adversarial audit sub-agents plus my own reads
> re-covered: (a) the **stacking hot path** — `accumulator.py` (MinMaxReject k-insertion brute-forced against a
> reference impl at every n=0..3 × k boundary incl. NaN gaps, band denominators ≥1 + ±inf-seed masking, Welford
> online mean/var), `stacker.py` (κ-σ two-pass keep-mask both NaN widenings → can only ever yield an honest NaN gap,
> never a corrupted value; coverage sourcing; memory-guard plane charges; cancel paths), `drizzle_path.py`
> (`_clip_tolerance` neff/var-floor, CRPIX/CDELT super-res scaling re-derived, half-open pixmap bounds) — **CLEAN**;
> (b) the **solve/QC/ingest path** — Bayer green-extraction (all four patterns), float32-promote overflow guard, FWHM/
> eccentricity/transparency math + NaN guards, grading modified-z/meanAD/cap, streak reconcile (matches its documented
> known-buggy dilution, no new defect), ingest dedup/`_cache_stale`/`_refresh_frame_metadata`/`reset_frame_*`
> consistency — one NEW verified bug (below, **fixed this run**); (c) the **webapp auto-stack orchestration** —
> `pipeline.py` min-frames guard (no off-by-one), `_auto_stack_frame_count` marker/`prior_max` logic, auto-grade
> cumulative-cap denominator (no new leak), `jobs.py` queued-cancel race / cancelled-vs-error / `_recover_interrupted`
> (no double-run) / prune, `watcher.py` debounce + stranded-retry — one NEW verified bug (below, **filed for the
> Builder**). **(1) SHIPPED this run (v0.184.6):** a plate-solve *failure* clobbered a frame's `qc_error`/
> `qc_error_final:` reject_reason to `solve_failed:` (the guard's bare `accepted` term fired because QC-error frames
> stay `accept=True`), defeating the QC terminal-skip state machine and re-QC'ing corrupt files every scan forever —
> reproduced + fixed + regression-tested (struck below). **(2) FILED (open):** the auto-stack *pre-check* phase
> (`_auto_stack_frame_count`/`_mixed_pointing_check`/`_mark_auto_stack_attempt`) sits *outside* the per-target
> `try/except`, so a target deleted mid-scan (or a DB-lock) marks the whole pipeline job `error` and skips auto-stack
> for every remaining target — violating the documented "non-fatal per target" contract the QC loop already honours
> (reproduced by the audit; open bug below). Curation + 1 improvement idea + 1 new beginner feature filed below.
>
> **Re-audit — stacking engine (geometry/drizzle + calibrate/weighting) CLEAN again; shipped one verified solve bug
> (a second was a concurrent duplicate) (Scout 2026-07-23, branch `claude/kind-mccarthy-kjj0fu`).** Baseline suite green (**1817 passed, 2 skipped**).
> Three independent adversarial audit sub-agents re-covered the engine + the ingest/QC/solve path: (a) **stacking
> geometry/drizzle** — `accumulator.py` (WeightedSum/MinMaxReject band denominators ≥1 + ±inf-seed masking, Welford
> online mean/var), `drizzle_path.py` (CRPIX/CDELT super-res scaling re-derived exact, half-open `[-0.5,N−0.5]`
> bounds, pixmap axis order, two-pass rejection fed by separate stackers, `_clip_tolerance` keep-all guards),
> `mosaic.py` (RA-wrap `unwrap_ra_deg`, CRPIX pad, MAD outlier floor), `reference.py`, `pointings.py` — **CLEAN** (one
> non-corrupting note: drizzle `_clip_tolerance` Bessel uses the integer frame count vs the weighted effective sample
> size — affects only which contributions clip, never a covered pixel's value); (b) **calibrate + weighting** —
> `apply.py` (dark-then-flat raw-Bayer order numerically re-verified, bias never double-subtracted, exposure-scaled
> dark direction, `_FLAT_FLOOR` divide guard, NaN=no-correction), `masters.py` (`_sigma_clip_mean` all-NaN→NaN /
> mad=0 spike-reject), `weighting.py`/`photometric.py` (factors clipped `[0.1,1]`, inverse-variance `1/s²` fold
> direction + zero-guards — no NaN/zero/negative weight reaches the accumulator) — **CLEAN**. **Two NEW verified bugs
> found this run** (both struck below): (1) `solve_one` left an otherwise-solved frame with a NULL centre when ASTAP's
> `.ini` didn't parse — I fixed it, but the Builder shipped the **same** fix concurrently on `main` as **v0.184.2**
> (`wcs_center_deg_from_text`), a genuine duplicate, so at merge time I dropped my equivalent change and kept `main`'s;
> (2) the plate-solve **failure branch clobbered a real `reject_reason`** (`user`/`qc:`/`auto:streak`/`auto:grade:`/
> `bulk:`) to `solve_failed:` on any re-offered already-rejected frame, mis-attributing it in the reject-summary
> buckets and leaking the cumulative 25% auto-grade cap — **fixed + regression-tested + shipped this run** as a guarded
> write mirroring the success branch's self-heal contract (**v0.184.3**). One lower-confidence observation left unfiled
> (the `_cache_stale` size-only compare — inside the already-documented "reused source path" family), and one
> autonomy/efficiency idea filed (stop re-plate-solving deliberately-rejected frames every scan).
>
> **Re-audit — stacking engine CLEAN again; one NEW verified render/ingest preview-staleness bug filed
> (Scout 2026-07-23, branch `claude/kind-mccarthy-hhvyko`).** Baseline suite green (**1817 passed, 2 skipped**). Three
> independent adversarial audit sub-agents plus my own reads re-covered the engine + the render/ingest path: (a)
> **stacker.py orchestration** (κ-σ pass-1/2 keep-mask incl. both NaN widenings + the analytic proof a fully-covered
> pixel can't be nulled to a wrong value — only to an honest NaN gap; MinMaxReject `result()` band denominators ≥1 +
> ±inf identity masked before the add; coverage sourcing always 2-D from uniformly-3-D `coverage`; n=0/1/2/3 dispatch
> gates; memory-guard plane charges; cancel-mid-pass-1 → graceful cancelled result) — **CLEAN**; (b) **calibrate +
> combine + weighting** (`apply.py` flat-floor/`_sanitize_pedestal`/exposure=0/None/shape-mismatch guards,
> `masters.py` `_sigma_clip_mean` all-NaN→NaN / spike-reject convergence, `channel_combine.py` floored LRGB/RGB
> divisor + NaN-union, `weighting.py` factors clipped `[0.1,1]` + inverse-variance fold bounded, `photometric.py`
> `max_ratio`-bounded scale — the `star_count` unguarded-finiteness asymmetry examined and dismissed as benign, a
> SQLite INTEGER can't be NaN) — **CLEAN**; (c) my own reads of `reference.py` (the `is not None` centre filter makes
> NaN-poisoning unreachable; RA-unwrap median; pole `cos_dec=0` degeneracy correct) and `pointings.py` (isfinite
> guard, union-find path-compression, centroid-norm `or 1.0`, dot clamp) — **CLEAN**; (d) the **render/ingest path** —
> `output.py` (covered-only percentiles, NaN→0 only *after* stats, display-space FITS/TIFF/PNG/JPEG parity),
> `thumbnail.py` (NaN-aware stretch/downsample), `watcher.py` (size+mtime debounce, stranded-batch re-offer),
> `rejection_summary.py` + `frames.py` (used = accepted−unsolved / dropped = rejected+unsolved partition disjoint,
> nulls-last sort) — all **CLEAN**. **One NEW verified bug filed** (below): the frame preview/thumbnail cache keys on
> `frame_id` only and is **never invalidated on a Stage-1 cache refresh**, so under `copy_to_cache=True` a reused
> source path (or a completed truncated sub) keeps serving the OLD preview for that frame (broken-UX, Low/latent,
> traced; same `copy_to_cache`-gated family as the stale-plate-solution bug). Curation: re-verified two open bugs are
> still accurately described (the `copy_to_cache=False` staleness-recovery-DEAD bug — confirmed `config.py:65` +
> `ingest.py:194` gating; the History "Adjust" 0.10-vs-0.06 parity bug — confirmed `stretch.py:49` vs
> `output.py:421`). Added a new beginner feature ("Your imaging calendar" — a temporal capture-activity heatmap) and a
> friendliness improvement (a plain-language "?" explainer for the honest "N not located yet" badges) below.
>
> **Re-audit — full stacking/QC/solve/render sweep CLEAN again; two NEW verified bugs filed (Scout 2026-07-23,
> branch `claude/kind-mccarthy-54eyci`).** Baseline suite green (**1815 passed, 2 skipped**). Three independent
> adversarial audit sub-agents plus my own reads re-covered: (a) the **less-audited stacking helpers** — `mosaic.py`
> (RA-wrap canvas/CRPIX/outlier math reproduced clean across the 0°/360° seam and pole cases), `reference.py`,
> `output.py` (NaN=no-coverage → 0 across FITS/TIFF/PNG/render, all-NaN→zeros, no percentile over uncovered pixels),
> `pointings.py` — **CLEAN**; (b) the **QC + plate-solve path** — `metrics.py` (Bayer green-extraction layouts,
> float32-before-add overflow-safety, FWHM 2.35482·σ, flat-frame no-crash), `noise_ratio.py` (MAD estimator),
> `grading.py` (modified-z, single-pass 25% floor-`int()` cap distinct from the already-fixed cumulative bug),
> `astap.py`/`runner.py` — core math CLEAN; (c) the **render/webapp layer** — `thumbnail.py`/`output.py` autostretch
> NaN-awareness + preview↔export parity (byte-identical covered pixels for a display-space export), `frames.py`/
> `gallery.py` pagination/nulls-last/connection-safety, `watcher.py` debounce — CLEAN. My own reads of the auto-stack
> pipeline (`_auto_stack_frame_count`, `_auto_edit_process_run` parity) and the honest-accounting module
> (`rejection_summary.py` + its `frames.py` caller, `used = accepted − unsolved`) agreed — no new bug there.
> **Two NEW verified bugs filed** (both below): (1) a plate-solve **solved-but-null-centre** data-completeness bug —
> a frame ASTAP solves (valid `.wcs`) but whose `.ini` doesn't parse is persisted with `wcs_json` set yet
> `ra/dec_center_deg = NULL`, so it stacks but is silently excluded as the reference frame and from sibling-hint
> seeding, and is never re-offered to recover its centre (reproduced); (2) a render-suggestion **parity** bug — the
> History "Adjust" suggestion targets sky→0.10 while the stored STF gallery thumbnail targets sky→0.06, so "Adjust"
> opens ~2× brighter than the thumbnail it claims to match (reproduced, median 32 vs 15 /255). Curation + a new
> beginner feature ("Your imaging log") + a friendliness improvement idea (thin-stack caveat on Gallery/Dashboard
> tiles) filed below. Two comment/consistency nits (the `runner.py` unreadable-sidecar comment overstates "stops
> being re-offered"; `reference.py` lacks the `isfinite` centre guard `pointings.py` has — both effectively
> unreachable) noted in the Minor group.
>
> **Re-audit — stacking engine CLEAN again; shipped the SIMBAD nearest-row fix; filed one NEW verified ingest
> wrong-result bug + enriched the ⭐⭐ top bug with its minimum-frames code location (Scout 2026-07-23, branch
> `claude/kind-mccarthy-nqgrvr`).** Baseline suite green (**1805 passed, 2 skipped**). Three independent adversarial
> audit sub-agents plus my own reads re-covered: (a) the **stacking reduction/rejection core** — `accumulator.py`
> (MinMaxReject k-insertion brute-forced against a reference impl across every k=1..3 × n=0..8 boundary incl. NaN
> gaps = 0 mismatches; band denominators ≥1, ±inf seeds never leak; Welford n=1→NaN-var / n=2→(a−b)²/2 + `add`≡
> `add_window` no read-before-write aliasing; WeightedSum covered=weighted-mean / uncovered=NaN), `stacker.py` (κ-σ
> keep-mask σ=0/NaN widenings — proven it can only ever yield an honest NaN gap, never a corrupted value; below-
> threshold fallbacks correctly gated), `drizzle_path.py` (`_clip_tolerance` neff<3/var-floor/Bessel-on-true-count;
> `result()` no-re-divide); (b) **align/mosaic/calibrate** — `align.py` (CPU cval=NaN ↔ GPU cval=0 parity via the
> `inset≥1` interior-stencil argument + subpixel NaN re-mask), `mosaic.py` (RA-wrap circular mean, MAD ½-frame cap,
> CRPIX arithmetic), `calibrate/apply.py`+`masters.py` (dark-then-flat raw-Bayer order, exposure-scaled dark
> direction, `_dark_scaling_applies` shared predicate, MAD=0→robust-median) — **all CLEAN, no data-integrity bug**;
> and (c) the **watcher/ingest/QC/solve path**, which is where this run's findings came from. **Verified this run:**
> (1) **the shipped stale-plate-solution fix is DEAD on the default install** — all staleness recovery incl.
> `_refresh_frame_metadata` is gated behind `copy_to_cache`, which the webapp defaults to `False`
> (`config.py:65`→`pipeline.py:66`→`ingest.py:194`), so a source overwritten in place with different content keeps
> its old WCS and stacks at the wrong position (NEW bug filed below, wrong-result/latent, Low); (2) **the ⭐⭐ top
> bug has no minimum-frames floor anywhere in the auto-stack chain** — `_auto_stack_frame_count` returns any count
> ≥1, so a lone solved sub is auto-stacked + auto-edited + published unattended (precise locations added to the top
> entry). **Shipped:** the SIMBAD `_pick_nearest_row` fix (struck below; +3 offline regression tests). Non-bugs the
> audits noted and I did **not** file: the `_sigma_clip_mean` MAD=0 → robust-median on legitimately two-level
> quantized data (documented, deliberate — degrades to the median, never a hole); the truncated-mid-copy
> "successful-but-wrong QC metrics stuck forever" case (moderate confidence — depends on astropy raising on a
> truncated FITS read, which it usually does — not filed). Curation + a new beginner feature ("Reuse your favourite
> look") + an autonomy improvement idea (relaxed-parameter plate-solve retry, targets the top bug) filed below.
>
> **Re-audit — stacking engine + render/output CLEAN again; shipped a verified honest-accounting verdict fix and filed
> one NEW ⭐ Target-badge broken-UX bug (Scout 2026-07-23, branch `claude/kind-mccarthy-zkszg0`).** Baseline suite green
> (**1797 passed, 2 skipped** at run start; the STACKER-label bug I'd re-verified was concurrently fixed on `main` by
> the Builder as v0.179.2 — a genuine duplicate, so I dropped my equivalent code change and kept only my unique work).
> Two independent adversarial audit sub-agents plus my own reads re-covered (a) the **stacking hot path** —
> `accumulator.py` (MinMaxReject k-insertion brute-forced against a reference impl for k=1..3 across n=0..8, band
> denominators `count−2k`/`count−2` proven ≥1, ±inf seeds never leak; WeightedSum covered=weighted-mean / uncovered=NaN;
> Welford n=1→NaN-var / n=2→`(a−b)²/2` + `add_window` read-before-write ordering), `drizzle_path.py` (`result()` keeps
> the running weighted *average* — the STScI-correct non-divide; `_clip_tolerance` neff<3/flat-var/uncovered gating; the
> any-channel-OR `neff` overcount proven *benign*), `align.py` (CPU cval=NaN ↔ GPU cval=0 parity via the valid-mask
> bound + no `0*NaN` at the integer boundary; subpixel order-1 NaN re-mask), `mosaic.py` (RA-wrap circular mean, MAD
> ½-frame backstop, canvas caps, CRPIX pad), `weighting.py`/`photometric.py` (factors clipped `[min_weight,1]`, every
> zero-divisor guarded, inverse-variance fold correct) — **all CLEAN, no data-integrity bug**; and (b) the
> **render/output + rejection-accounting** path — `output.py` (covered-only percentiles, FITS/TIFF/preview + display-space
> parity), `thumbnail.py` (NaN-excluding stretch, monotone black slider, `_midtones_for`≡inverse-MTF), `frames.py`
> (reject-summary/setup-banner tallies, nulls-last sort, offset/limit clamp, connection-leak-safe try/finally,
> missing-target→404), `grading.py` (modified-z + `MAX_REJECT_FRACTION` cap) — all correct. The render/router audit
> surfaced **two verified broken-UX bugs in the frame-accounting UX** (the ⭐⭐ thin-stack honesty family): I
> **fixed + regression-tested + shipped** the 50/50-split verdict (`unsolved >= used` → strict `unsolved > used`; struck
> below), and **filed** the Target-page pill bug (hides the unsolved count whenever any frame is also rejected — a small
> frontend fix left for the Builder, ⭐ below). Curation + a new beginner feature ("What else is in this picture?") + an
> image-quality improvement idea (small stacks get no outlier rejection) filed below. (Non-bugs the audits noted and I
> did **not** file: the float32 `_sum` ~1e-7 relative rounding on huge stacks — documented tradeoff far below read noise;
> `_downsample_rgb` NaN-floor edge-darkening — effectively dead code, no production caller feeds it NaN;
> `render_sub_preview` box-vs-strided noise understatement in the one-sub reveal — conservative direction, headline ratio
> measured at native res.)
>
> **Re-audit — stacking engine CLEAN again; shipped a verified plate-solve-banner broken-UX bug in the ⭐⭐ family;
> filed one cosmetic STACKER-label bug (Scout 2026-07-23, branch `claude/kind-mccarthy-hn18nz`).** Baseline suite
> green (**1795 passed, 2 skipped**). Two independent adversarial audit sub-agents plus my own reads re-covered the
> engine and the webapp/ingest/QC/solve path. (a) The **stacking hot path is CLEAN** — the reduction/rejection core
> (`accumulator.py` MinMaxReject k-insertion verified at every count boundary incl. the shared min/max view writes +
> tie-safety, κ-σ keep-mask NaN widenings, Welford `add`≡`add_window` sub-view ordering, WeightedSum inverse-variance
> combine), `drizzle_path.py` (`_clip_tolerance`/neff/var-floor/pixmap-bounds), `align.py` (CPU cval=NaN ↔ GPU cval=0
> parity, subpixel NaN mask), and `calibrate/apply.py`+`masters.py` (dark-then-flat raw-Bayer order, bias never
> double-subtracted, no-data pedestal masks) all match the repeatedly-clean documented state — **no new data-integrity
> bug.** (b) The **webapp/solve audit found a verified, reproduced broken-UX bug** directly in the ⭐⭐ plate-solve
> family: the "install ASTAP / star database" **setup banner was dead** — plate-solve failures are stored
> `solve_failed:…` but leave the frame **accepted** (`accept=1`), while `reject_reason_counts()` (which feeds
> `_solve_setup_problem`) tallies only `accept=0`, so the detector never saw them and a first-light user with no star
> DB was told to "Run Plate Solve" (the very thing failing) with no guidance. **Reproduced + fixed + regression-tested
> + shipped this run** (struck below): added `Project.solve_failure_reason_counts()` (accept-agnostic tally of
> `solve_failed:` reasons over `wcs_json IS NULL` frames) and fed it to the setup detector. (c) One **cosmetic
> provenance bug** filed below — the `STACKER` FITS header/History badge mislabels the method on a below-threshold
> stack (n<3 min-max / n<4 κ-σ silently fall to plain mean, but the header still says the rejection method). Curation +
> a new beginner feature (storage headroom) + an improvement idea filed below.
>
> **Re-audit — stacking-engine hot path CLEAN again; one NEW verified render/parity broken-UX bug in the "one frame
> vs your stack" reveal (Scout 2026-07-23, branch `claude/kind-mccarthy-ltki02`).** Baseline suite green
> (**1784 passed, 2 skipped**). Two independent adversarial audit sub-agents plus my own reads re-covered the engine
> and the render/output path: (a) the **stacking hot path is CLEAN** — `accumulator.py` (MinMaxReject k-insertion +
> degrade bands + `rejection_counts` schedule traced against the closed form at counts 5/3/1/0; Welford `add`≡
> `add_window` sub-view writes proven non-aliasing; WeightedSum `sum/w>0`-else-NaN + any-channel coverage),
> `stacker.py` (κ-σ keep-mask σ=0/NaN-mean widenings, the analytic proof κ-σ can't null *all* contributions at a
> pixel, memory guard plane-count charge, inverse-variance photometric combine, cancel handling), `drizzle_path.py`
> (`_clip_tolerance` float64/Bessel/`16·eps·m²` unresolved-floor, `neff` on the true `_count`, half-open bounds,
> per-channel footprint OR, `result()` NaN-mask), `align.py` (CPU `cval=NaN` ↔ GPU `cval=0` parity via the
> `inset≥1` interior-stencil argument, subpixel-shift order-1 NaN re-mask) — all matching the repeatedly-clean
> documented state (the `n_used=min(p1,p2)` frame-count under-report on a pass-1-fail/pass-2-succeed frame is the
> known honest-accounting note, image is correct). My own reads of `calibrate/apply.py` (the `_dark_scaling_applies`
> shared predicate holds), `qc/grading.py` (per-call 25% cap + practical-significance floors), `qc/streaks.py`,
> `solve/runner.py` (the unreadable-sidecar → `solve_failed` self-heal), and `webapp/watcher.py` +
> `pipeline.py::submit_process_target` agreed — no new engine bug. (b) The **render/output audit found ONE new
> verified broken-UX bug** (re-verified by me against the code): the **"one frame vs your stack" reveal renders its
> two halves under different tone curves** once a custom preview stretch is saved (`save_stack_preview` writes an
> `asinh` preview while `reference_sub_png` stays hard-coded STF), and always for a display-space editor-export run —
> filed as the ⭐ render/parity entry below, **traced**. Curation + a new beginner feature + an autonomy improvement
> idea filed below.
>
> **Re-audit — stacking-engine reductions + calibrate + align + bg all CLEAN, no new bug (Scout 2026-07-23, branch `claude/kind-mccarthy-bt8ehb`).**
> Baseline suite green (**1775 passed, 2 skipped**). Two independent adversarial audit sub-agents re-read the engine
> end-to-end and both came back **CLEAN**, matching the repeatedly-clean documented state: (a) the reduction/rejection
> core — `accumulator.py` (WeightedSum `sum/w>0` else-NaN + any-channel `frame_coverage`; MinMaxReject re-verified
> across counts 0–7 at k=3 against the closed-form per-band expectation incl. `rejection_counts` drop schedule and
> the `[full]`-before-add inf-safety; Welford mean/var ≡ `nanmean`/`nanvar(ddof=1)` and the `add_window` sub-view
> writes proven equivalent to full `add`), `drizzle_path.py` (`_clip_tolerance` `+inf` for `wht==0`/`neff<3`/below the
> `16·eps·m²` float32 var-floor, Bessel on the true `_count`, float64 `m2−m²` anti-cancellation, half-open
> `[-0.5,N-0.5]`, per-channel OR footprint, `result()` NaN-mask), `weighting.py`/`photometric.py` (factors clipped to
> `[min_weight,1]` so log/geo-mean never ≤0; scales bounded `[1/max_ratio,max_ratio]`; `MIN_MEASURED_FRAMES` neutral
> fallback; the `1/s²` fold composes into a correct inverse-variance weighted mean), and `mosaic.py` (RA-wrap circular
> mean/`unwrap_ra_deg` seam-safe, MAD drop capped at half the frames, canvas px/MP caps, `crpix−x_min+1` CRPIX shift);
> (b) the per-frame path — `calibrate/apply.py` (dark-then-flat raw-Bayer order, `_FLAT_FLOOR=0.1`→1.0 divide guard,
> `bias+(dark−bias)·(t_light/t_dark)` scaling with the no-data pedestal restores numerically re-verified, and the
> exposure-mismatch warning gated on the *same* `_dark_scaling_applies` predicate as the scaling — the v0.176.1 fix
> holds), `calibrate/masters.py` (`_sigma_clip_mean` MAD=0→tol=0 spike-reject, NaN-aware combine), `align.py` (the CPU
> `cval=NaN` vs GPU `cval=0` divergence proven un-reachable on the production windowed path by the
> `FRAME_EDGE_INSET_PX=3` interior-stencil argument; the only exact-boundary site is the caller-less non-windowed
> `reproject_rgb`; subpixel-shift NaN propagation with the matched order-1 mask), and `bg/*` (shared CPU/GPU
> `_suppress` core, coverage/gradient sky models finite-only). NaN=no-coverage, rejection math, memory bounds and
> preview↔export parity all hold. My own reads of `accumulator.py` and `webapp/rejection_summary.py` agreed. **No new
> verified engine bug this run.** One maintainability note (dead caller-less `reproject_rgb` carrying a latent CPU/GPU
> `cval` parity hazard) filed under Infra; curation + a new beginner feature + an improvement idea filed below.
>
> **Re-audit — stacker.py orchestration CLEAN; shipped a new calibration broken-guardrail bug (Scout 2026-07-23, branch `claude/kind-mccarthy-449g7g`).**
> Baseline suite green (**1771 passed, 2 skipped**). Two independent adversarial audit sub-agents re-read the hot path
> again end-to-end: (a) `stacker.py` (1905 lines — κ-σ pass-1/2 keep-mask incl. both NaN widenings, the `consume_clipped`
> rejection tally units, the memory guard's `dst_shape`/`reject_arrays`/post-lucky-`n` accounting, coverage sourcing per
> path, `_imap_bounded` in-flight bounding, cancel handling on all four standard branches, quick-look/reel caps) — **CLEAN**,
> matching the documented state (the STACKER-label-on-degraded-method and the pass-1→pass-2 transient are the known
> label-only / already-filed-memory-guard notes, not new bugs); (b) `render/thumbnail.py` (asinh/STF stretch, `_downsample_rgb`
> NaN floor, striding preview parity) and `output.py` (FITS/TIFF/preview parity, display-space card, `_to_uint16_linear`
> covered-only percentiles) read clean too. The **one new verified bug** this run was in `calibrate/apply.py`: the
> exposure-mismatch advisory (`calibration_warnings`) gated scaling on "a bias is present", but `_effective_dark` only
> *actually* scales when the bias **shape matches the dark** — so a loaded-but-wrong-shaped bias fell back to the unscaled
> dark (over/under-subtracting a mismatched-exposure pedestal on every frame) **while silencing the very warning meant to
> catch it**. Reproduced (30 s dark on 10 s subs, 2×2 bias vs 4×4 dark → effective dark 300 not the scaled 166.67, warnings
> `[]`), **fixed + regression-tested + shipped this run** (struck below): extracted a shared `_dark_scaling_applies` predicate
> used by both sites so they can't drift again. Curation + 2 ideas filed below.
>

### Checked, not a gap (Builder 2026-09-04) — from "Autonomy & friendliness"

- **⚪ CHECKED, NOT A GAP — recorded so the next run doesn't "fix" it (Builder 2026-09-04, while shipping
  v0.346.0).** The stationary-streak guard needs its clustered frames to span an hour, which a beginner's
  *first short session* cannot supply — so it looks as though a one-hour target is stranded. It is not:
  `reconcile_streak_rejections` runs on **every** scan that runs QC and reads the **whole** target, not only
  the new frames, so night two's scan reconciles nights one and two together and the span is met retroactively.
  The frames are rescued before the next stack either way. Do not add a per-session fallback; a shorter span is
  exactly the threshold that would start re-accepting Starlink trains.

### Sweep complete: the "a six-hour gap is not a night" class — from "Autonomy & friendliness"

- **⚪ SWEEP COMPLETE — the "a six-hour gap is not a night" class has four sites and all four are now
  answered; here is the list so nobody re-walks it (Builder 2026-09-04).** The generative test is cheap
  enough to keep applying to *new* code, but a repository-wide re-sweep is spent. **A candidate is any
  statistic computed over `_split_sessions` / `session_end_stamps` output that is then *called a night*, or
  *counted* as one.** Every site, and its answer:
  - `recent_night_pace_s` — **fixed v0.329.4** (a split night halved the pace; a short one vanished under
    `MIN_PRODUCTIVE_NIGHT_S`).
  - `nights_breakdown`'s rows — **fixed v0.342.0** (two rows carrying one date, with a "Set this night
    aside" button that acted on half of it).
  - `early_stop`, on both surfaces — **fixed v0.342.3** (the prior-*night* floor counted sessions, so two
    split nights invented a habit; and the median was diluted by mid-night stops).
  - `library_session_recap` — **fixed v0.342.4** (the Dashboard's "Last night" card reported half a night).
  - `session_recap` — **fixed v0.345.0** (the entry above). Not a defect in the statistic, which was honestly
    session-shaped; a defect in showing it next to a night-shaped one under a shared date. Resolved by making
    the *card* night-shaped and renaming it "Last night" — the statistic keeps its session answer for any
    caller that passes no `night_of`. **So the class is now closed on all five sites.**
  Everything else that splits sessions either *is* asking a session question (`last_session_frames`,
  `recent_session_window_frames` — a memory bound) or already takes a `night_of`.

### Measured: rejection-outlook sizing (Builder 2026-09-03) — from "Autonomy & friendliness"

- **MEASURED, RECORDED SO NOBODY RE-MEASURES (Builder 2026-09-03, while sizing the rejection-outlook
  endpoint) — `cluster_pointings` costs 1.58 s at the owner's largest target, and a mosaic stack pays it
  twice.** *(No code change wanted yet — this is a perf note with numbers, not a task. Pillar: performance,
  and only with a measurement.)* Timed on a synthetic 4-panel mosaic with the owner's real sub count: 500
  subs → 0.01 s, 1,000 → 0.05 s, 2,000 → 0.21 s, **5,477 → 1.58 s** (the clean O(n²), pure Python). That
  confirms the `auto_reject_depth` docstring's "~2.4 s" order of magnitude and its decision to grid-snap
  before clustering (which takes it to under a millisecond). **What the note adds:** on a mosaic canvas the
  *unsnapped* path still runs twice per stack — `compute_frame_weights` and `compute_photometric_scales` each
  call `pointing_groups` over the full frame list, with the same radecs and the same
  `PANEL_LINK_DIST_DEG`, so a 5,477-sub mosaic spends ~3 s clustering the identical points into the identical
  labels. Beside a stack that runs for many minutes this is noise, which is why nothing is filed as a task.
  **If a future run ever wants it:** the fix is to compute the labels once in `run_stack` (where
  `is_mosaic_canvas` is already known) and pass them down, *not* to grid-snap those two — their soundness gate
  is `min_members` over the real population, and snapping changes which frames count toward it. Do not start
  this without a profile showing the stack is actually pointing-bound.

### Measured and closed: the Library page's duplicated hygiene walk — from "Autonomy & friendliness"

- **⚪ MEASURED AND CLOSED — the Library page's duplicated hygiene walk costs ~196 ms per refresh on the
  owner's own shape, so do NOT cache it (Builder 2026-09-07, v0.374.6). Entry, method and numbers in
  [`SHIPPED.md`](SHIPPED.md); do not re-measure.**

### Closed as a non-finding, run not read (Builder 2026-08-31) — from "Autonomy & friendliness"

- **⚪ CLOSED AS A NON-FINDING — RUN, NOT READ (Builder 2026-08-31, branch `claude/wizardly-feynman-isps6l`).
  ~~A lowercase `<T>_mosaic/` folder would collide with the `<T> (mosaic)` target's safe name.~~ It would not:
  the Library has handled this for a long time, and there is a test on it.** The entry's arithmetic is right —
  `make_safe_name("M 3 (mosaic)")` and `make_safe_name("M 3_mosaic")` are **both** `M_3_mosaic` — but
  `make_safe_name` is not what decides a target's folder. `Library._allocate_safe_name` does, and it exists for
  exactly this: it keeps the readable name only when it is free *or already owned by this same display name*,
  and otherwise appends a stable hash of the display name. **Run both ways round on a real `Library`:** the
  first-registered target gets `M_3_mosaic` and the second gets `M_3_mosaic-3417e3ef` (or `-dfffdc4f` in the
  other order) — two display names, two project directories, in either order. **Already pinned**, by
  `tests/test_library.py::test_names_differing_only_in_punctuation_do_not_merge` (`M 31` vs `M_31`) and
  `…::test_all_unicode_names_get_distinct_targets`, which cover this as a *class* rather than as the two
  instances. So there is nothing to detect and nothing to report; the "cheap, safe slice" the entry proposes
  would be a nudge about a collision that cannot happen. **Read `_allocate_safe_name`, not just
  `make_safe_name`, before re-filing anything in this shape.**

    *(Original entry follows.)* **LATENT HAZARD (Builder 2026-08-30, spotted while wiring mosaic duplicates to their base target for
  v0.319.3 — traced, NOT reproduced, do not "fix" it blind) — a lowercase `<T>_mosaic/` folder would collide
  with the `<T> (mosaic)` target's safe name.** *(Pillar: correctness / data integrity — PRIORITY 4. Size: M,
  and most of that is deciding what is even safe to do. Confidence: the collision is arithmetic;
  whether any device produces the input is unknown.)*
  `make_safe_name` replaces every non-`[A-Za-z0-9._-]` run with `_`, so `"M 3 (mosaic)"` → `M_3_mosaic` — and a
  target literally named `M 3_mosaic` maps to **the same safe name**. Two different targets, one project
  directory. It does **not** bite the owner today only because `make_safe_name` deliberately preserves case and
  their device writes the output folder as `M 3_MOSAIC` → `M_3_MOSAIC`. A firmware (or a hand-renamed folder)
  that spelled it lowercase would land the on-device mosaic output and the real mosaic target on one another.
  **Why not to fix it here:** changing `make_safe_name`'s output is a rename of on-disk directories, which §9
  rules out outright, and the registry's own collision handling is the thing to read first
  (`Library.create_target` raises `FileExistsError`; what an *ingest* does with that is the real question).
  **The cheap, safe slice if this is ever taken:** detect the collision at scan time and *report* it (a
  cleanup-style nudge naming both folders) rather than silently merging two objects into one project.
  **Grep before starting:** `make_safe_name`, `open_or_create_target`, and the `(mosaic)` suffix in
  `_apply_seestar_convention`.

### Process note (Builder 2026-08-30): why the v0.317.1 bug survived a sweep — from "Autonomy & friendliness"

- **⚠️ PROCESS NOTE (Builder 2026-08-30, the reason the v0.317.1 bug survived a whole sweep of its own class)
  — a comment that asserts agreement with a *sibling* is a drift hazard, and a test that freezes the current
  behaviour turns it into a permanent one.** The two Target-page share calls carried the comment *"the same
  date `LatestPictureCard`'s share text uses for the same picture"*. It was true when written. When that card
  was fixed the comment stayed, and now read as a reassurance that the site had already been handled — so a
  sweep that greps for the *bug* finds a site that documents itself as correct. Compounding it,
  `Target.test.tsx` asserted the caption equalled `sharePictureText("M42", formatStampDate(stamp))`, i.e. it
  pinned the wrong stamp precisely. **The lesson worth generalising:** where two call sites must agree, make
  them agree *by construction* — one shared value (the page now computes `captureLabel` once) or a type
  (v0.317.2) — never by a comment naming the other one. And when a sweep of a class leaves a site untouched,
  check whether a *test* is asserting the old behaviour there; that is what makes a missed site invisible
  rather than merely unfixed.

### Dogfood baseline, 2026-08-30 — from "Autonomy & friendliness"

- **⚪ DOGFOOD BASELINE (Builder 2026-08-30, `scripts/agent-dogfood.sh`, recorded so the next IA slice has
  numbers rather than an impression) — nothing overflows and nothing errors; the tallest page is now the
  Target page.** Full-page scroll heights on a booted app with the bundled sample loaded and processed:
  **phone** `/targets/<t>` 3035 px · `/life-list` 3008 px · `/targets/<t>/edit/1` 2775 px · `/` 1813 px ·
  `/targets/<t>/stack` 1712 px; **desktop** `/targets/<t>` 2010 px · `/targets/<t>/edit/1` 1767 px ·
  `/life-list` 1453 px. The probe reports **no horizontal overflow on any page and no console errors**. For
  scale: the life list was **14,584 px** on a phone before v0.307.0 and Settings was 5,827 px before v0.266.0,
  so the five named IA slices plus those two have taken the app's worst page from ~24 phone screens to ~5.
  **What this says about "don't start Library/Editor speculatively":** it still holds — neither is the wall.
  The Target page is the tallest thing left, and it is tall because it is genuinely the page with the most on
  it, not because anything is stacked badly. One real friction *was* found on it this run and is fixed
  (v0.317.1); nothing else in the screenshots reads as a layout problem.

  **↳ RE-MEASURED four days and ~80 versions later (Builder 2026-09-03, at v0.338.1) — the numbers have not
  drifted, and the probe is still clean.** Same script, same sample, same two viewports: **phone**
  `/targets/<t>` **3014 px** (was 3035) · `/life-list` **3008** (unchanged) · `/targets/<t>/edit/1` **2829**
  (was 2775) · `/` **1785** (was 1813) · `/targets/<t>/stack` **1748** (was 1712); **desktop**
  `/targets/<t>` **2010** (unchanged) · `/targets/<t>/edit/1` **1805** (was 1767) · `/life-list` **1453**
  (unchanged). Still **no horizontal overflow on any page and no console errors**. So roughly eighty versions
  of feature work — every one of which could have appended a banner — moved the worst page by **21 px**, which
  is the `NoticeBoard`/`InsightTabs` grouping doing exactly the job it was built for. **The conclusion for the
  next run is the same as last time and now has a second data point behind it: do not open a speculative IA
  slice.** The two pages that grew (editor +54 px, stack form +36 px) grew inside their existing groupings,
  which is the intended shape.

  **The eyeball pass over the 42 screenshots found no new friction worth filing**, which is the honest result
  and is recorded so the next run does not re-walk it. Two things were checked and dismissed rather than
  filed, with the reason, so they are not re-investigated: (1) the Tonight page's **Night** picker renders as
  `mm/dd/2026` rather than `mm/dd/yyyy` — that is Chromium pre-filling the one field its `min`/`max` pin to a
  single value, not a partially-set value, and it is *more* helpful than the placeholder, not less; (2) the
  Storage page's stacked bar labels its two segments `cache` and `data` while the text above says "cache" and
  "output", and the `data` segment is the 5 MB remainder (outputs + DBs + thumbs) rather than the 3 MB of
  outputs — a wording mismatch of a bar nobody reads for numbers, below the bar for a change on a live install.

### Audit note (Builder 2026-08-30): the first two "normalises against its own" candidates — from "Autonomy & friendliness"

- **⚪ AUDIT NOTE (Builder 2026-08-30, first two candidates of the v0.312.1 "normalises against its own
  subset" QA lead — NON-findings, recorded so nobody re-treads them).** The lead directly above asks for a
  sweep of every statistic whose normalising subset is data-dependent. Two of its named candidates were read
  this run and are **not** instances; both were traced to *why* their subset is stable rather than merely
  looking plausible. (1) `edit/starmask.py:67` — `np.percentile(tophat[cover], 99.9)`: `cover` is
  `np.isfinite(lum)`, i.e. "pixels that have data at all", which is a property of the **canvas** and not of
  how much data went in. A fixed quantile over it does not drift with the sub count the way the tint's
  `p90(non-empty)` did, because the non-empty set there *grew into* the noise floor as subs accumulated
  while `cover` does not change at all. (2) A repo-wide grep for the lead's own pattern
  (`np.percentile(x[…])` with a data-dependent mask) finds **only** that one site across `seestack/` and
  `webapp/` — 35 percentile calls, 34 of them over a whole array. *(Confidence: read and grepped, not
  measured — the lead's own method is to measure at 16 / 64 / 300 subs, and these two were ruled out on the
  stronger ground that their subset is not a function of the sub count at all. The **unswept** half is the
  lead's other axis: the auto-grade / auto-edit strength pickers and `stackhealth`'s verdicts, which reach
  for a fraction of "affected" pixels rather than a percentile, and which a `np.percentile` grep does not
  see.)*

### Process note (Builder 2026-08-30): the pristine-checkout measurement — from "Autonomy & friendliness"

- **⚠️ PROCESS NOTE (Builder 2026-08-30, measured on a *pristine* checkout after it cost a chunk of a run) —
  running a hand-picked list of test files that **interleaves `tests/webapp/…` and `tests/…` paths** can make
  pytest lose `tests/webapp/conftest.py`, and every later webapp test errors with `fixture 'client' not
  found`.** *(Not a bug in the app, not a bug you introduced, and NOT a reason to touch conftest.)* Reproduced
  on `origin/main` with nothing of mine in the tree:
  `pytest -q tests/webapp/test_deepening_reel.py tests/test_output_archive.py tests/webapp/test_wallpaper.py`
  → *7 errors*, while the same three files in a different order, or the whole suite in one go
  (`pytest -q`, one `tests/` argument), are green. It is an argument-ordering quirk of conftest resolution
  across the two package dirs, and it looks exactly like "my change broke every webapp test", which is how it
  eats time. **What to do:** if a targeted run errors like this, re-run it with the webapp files *last* (or on
  their own) before believing it — and treat the full-suite run as the only authority, which §5 already says.

### Process note + two follow-ons (Builder 2026-08-27, Sky-map North-up convergence; follow-on (b) measured and deliberately left unshipped) — from "Autonomy & friendliness"

- **⚪ PROCESS NOTE + TWO FOLLOW-ONS (Builder 2026-08-27, branch `claude/compassionate-galileo-xhognz`) — I
  built the v0.289.0 Sky-map North-up fix concurrently and STOOD DOWN on it when I synced to merge; recorded
  because the convergence is the useful signal, and because two small things I had are not in what shipped.**
  *(Third such collision in three days — see the same note under the video-crop entry. The claim-it-in-**In
  progress**-first rule in AGENTS §11 is what would have caught it, and neither of us did it.)*
  Two independent reads reached the *same* design down to the function names: an additive
  `preview_north_up_deg` column, an `applied_north_up_deg` helper folding the threshold + 90° snap into one
  number, `rotate_mask_north_up` mirroring the picture's `np.rot90`/PIL split, and a derived affine composed
  into the tile's CD/CRPIX — both pinned by the same round-trip (mark a pixel, rotate for real, check a known
  RA/Dec lands on it; mine measured 0.10 px worst error over 8 angles × 4 positions, theirs ~1 px against
  nearest-neighbour rounding). When one bug's fix is re-derived identically twice, the shape really is the
  natural one. Theirs landed first, so I dropped mine wholesale rather than merge two implementations of one
  fix; what follows is only what mine had that theirs does not.

  **(a) ✅ SHIPPED (Builder, v0.292.2, branch `claude/compassionate-galileo-mkzo0l`)** — built exactly as
  specified, including the two cases it said must stay silent. New `webapp/preview_orient.py` answers "what
  rotation do this run's *stored bytes* actually carry?" — the recorded angle when there is one (an explicit
  `0.0` included: that is a statement the auto-edit rewrite makes, not an absence), and otherwise a **check**,
  never a guess: work out the grid the preview would sit on un-turned (`preview_grid_size` off the run's own
  `canvas_w`/`canvas_h`, so the common answer costs one PNG *header* read and no FITS access at all), and
  believe a rotation only when the stored PNG's dimensions are exactly `north_up_pixel_transform`'s output for
  the angle that run's own WCS implies. Wired into all five readers that map bytes↔sky: the Sky map's
  placement (`routers/sky.py`), `sky-overlay`'s alpha, the share JPEG, the wallpaper crop and baked marks
  (`routers/stack.py`), and the run listing's `preview_north_up_deg` — that last one is the half the note
  didn't mention and it fixes a *visible* bug: History keys "hide the object pins and scale bar" off that
  field, so a legacy North-up picture was being annotated in the wrong places.
  **Deliberately silent, as the entry required:** an exact-180° save (the dimensions don't move, so there is
  nothing to measure) and a cropped preview (an auto-edit border trim leaves it on neither grid) both read as
  un-rotated — i.e. exactly what the code did before — so an unrecognised run is never placed *more* wrongly
  than it already was. **Upgrade-safe (§9):** read-only, no schema/config/on-disk/API-shape change; a recorded
  angle is passed through verbatim so nothing about a current install moves.
  **Tests (+8 in `tests/webapp/test_preview_orient_legacy.py`, 5 fail before):** the recovery itself; an
  ordinary run untouched; a recorded `0.0` beating a recoverable rotation; the cropped-preview no-claim; and
  end-to-end — `sky-overlay`'s alpha matching the visible footprint, the run listing reporting the angle, the
  listing staying `null` for an ordinary run, and the Sky tile's extent swapping axes with the picture. The
  fixture is the existing `test_sky_north_up` mosaic, saved North-up for real and then had its angle column
  nulled — the exact pre-v0.288 state.

  Original spec, for the record:

  **A preview saved North-up *before* the column existed is still misplaced, and it need not be.** The
  shipped reader treats `preview_north_up_deg IS NULL` as "no rotation", so an install upgrading onto this
  build keeps drawing an old North-up-saved run at the master's orientation until someone happens to re-save
  it. That is *guessable-free*: the only thing that ever rotates a stored preview is this save, and its angle
  is a deterministic function of the run's own WCS (`applied_north_up_deg`), so a reader can **check** rather
  than guess — compute the un-rotated preview grid from the master's dimensions (the 1024 px cap rule in
  `load_stack_rgb`), and believe the rotation only if the stored PNG's dimensions are
  `north_up_pixel_transform`'s output size for that angle. *(Size S. An exact-180° legacy save is the one case
  that can't be told apart — it leaves the dimensions alone — and must read as un-rotated, i.e. exactly what
  the code does today; anything else whose size can't be accounted for must too, so an unrecognised run is
  never placed **more** wrongly than it already is.)* **Test:** a run with rotated pixels and a NULL angle gets
  an alpha matching its visible footprint; an ordinary run is byte-for-byte unchanged.

  **(b) ✅ MEASURED, AND DELIBERATELY LEFT UNSHIPPED (Builder 2026-08-29) — the reorder is a real win; here
  are the numbers so nobody has to measure it again.** On a 576 MB master (8000×6000 float32 ×3) with a 37°
  (non-snap) North-up angle, comparing today's `rotate_mask_north_up(stack_coverage_mask(fits), 37°)`-then-
  resize against decimating to the flat preview grid **first** and rotating there:

  | order | wall | peak Python allocation |
  | --- | --- | --- |
  | rotate at full res, then resize (today) | 0.67 s | 288.3 MB |
  | resize to the preview grid, then rotate | 0.13 s | 144.0 MB |

  Both produce the **same output shape** (1230×1280, from a 1024×768 flat grid), and they disagree on
  **0.034 %** of pixels — the alpha boundary moving by a pixel, exactly the cost this entry predicted.
  **Why it is not shipped:** the win only materialises on a path that needs a North-up save *at a
  non-orthogonal angle* (the 90° snap goes through `np.rot90`, already a single copy) on a very large mosaic,
  and it trades a hard alignment guarantee — the property this whole family of bugs kept breaking — for
  memory that a box which just held the 576 MB master demonstrably has. A future run that wants it now has
  numbers instead of a hunch; the change is ~6 lines in `sky_overlay`, plus the same shape wherever "My map"
  reads a run's mask. **Gate it on `crop is None`** — a cropped preview's flat grid is not
  `preview_grid_size(canvas)`, so mixing the reorder with the crop's own rounding adds a second alignment
  surface for no extra win.

  Original spec, for the record:

  **(b) The coverage mask is rotated at full canvas resolution, and could be decimated first.** `sky_overlay`
  now does `rotate_mask_north_up(stack_coverage_mask(fits), angle)` — a whole-canvas rotate whose output is
  then resized down to the ~1024 px preview grid inside `overlay_rgba_png` anyway. On a nine-figure-pixel
  mosaic that is a couple of extra full-footprint allocations on the RAM-capped box the stack path is
  memory-bounded for. Decimating to the preview grid *first* (the order the render itself uses — downscale,
  then rotate) removes them. **Gate it on a measurement, and be honest that it is not free:** NEAREST
  resample-then-rotate is not bit-identical to rotate-then-resample, so this moves alpha edges by up to a
  pixel. Only worth doing if the peak-RSS win measures real on a big master — otherwise close it. *(Size S.)*

### Process note (Builder 2026-08-27): two Builders built the grainier-restack nudge — from "Autonomy & friendliness"

- **⚠️ PROCESS NOTE (Builder 2026-08-27) — two Builders independently built the grainier-restack cover nudge in
  the same hour, from the same backlog entry, and one run's work was thrown away.** *(Not a feature — a
  coordination lesson worth one paragraph, per AGENTS.md §11.)* Branch `…-z1yulm` shipped `grainier_newest`
  (v0.281.0) while `…-c43ksl` built a functionally identical `grainier_default` (same bar, same
  best-earlier-run choice, same round-down, same one-tap `set-cover`); the second was reverted unmerged. §11's
  claim-by-moving-to-**In progress** rule is exactly what would have prevented it, and *neither* run did it —
  including this one. The cost is real (a full task's worth of engine + endpoint + component + 22 tests), so:
  **move the item to "In progress" with your branch name in the commit that starts it, and push that commit
  early** — a claim that only exists locally until the task is finished claims nothing. Cheap extra insurance
  for a small item: `git fetch` and re-read the entry right before you start writing code, not just at the top
  of the run.

  **It happened again the same day — and this time the *rules worked*.** A Builder (`…-galileo-0wtz21`) and a
  Scout (`…-knuth-qtz5h4`) both fixed the exact-0 debayer bug within an hour, arriving at functionally identical
  positional-mask fixes. The Scout's landed on `main` first, so the Builder **took `main`'s implementation
  wholesale** and dropped its own — no re-litigating whose was nicer, no near-duplicate code, and the version
  number the Scout had already used (`v0.284.5`) was left alone. The one thing it kept was the piece that was
  genuinely *different in kind*: a test checking every pixel of all three channels against an independent
  per-pixel reference debayer, next to the Scout's single-pixel probe. **That's the general rule when you lose
  this race: take what's on `main`, keep only what's additive, and say so in the merge.** Note also what neither
  agent's *fix* cost — the loser here spent one commit, not a run, because the duplicate was noticed at the
  pre-merge sync (§11) rather than after merging. Both halves of the lesson stand: claim the item early, *and*
  make the sync cheap to lose.

### Note (Builder 2026-08-08): learned shipping v0.251.0 → v0.252.1 — from "Autonomy & friendliness"

- **NOTE (Builder 2026-08-08, learned the hard way while shipping v0.251.0 → v0.252.1 — read this before injecting
  ANY option on the walk-away path).** Injecting an option for the user is not just a stacking decision, it is a
  *messaging* decision, and the second one is easy to miss. `quality_weighted` looked purely additive right up until
  the History surface was traced: on a stack whose saved defaults already name `min_max_reject`, the injected
  weighting is ignored by that rank-based combine, the run stamps `WGTSKIP` with `auto=False`, and
  `weightingSkippedText` (`History.tsx:263`) tells the user to *"use sigma clipping instead if you want your best
  subs to count for more"* — advice to undo a setting they never chose, about a picture that is byte-for-byte what
  it would have been anyway. The stacker was right; the *sentence* was wrong. **Rule for next time:** before
  auto-enabling an option, grep for every provenance key it can cause the run to stamp (`WGT*`, `PHOT*`, `REJ*`,
  `STACKER`…) and read the copy each one renders, with `auto` both true and false. The engine's own honesty
  machinery — which stamps *why* something didn't apply — is what turns a silent no-op into a confusing message.

### Engine QA note (Builder 2026-08-08) — from "Autonomy & friendliness"

- **ENGINE QA NOTE (Builder 2026-08-08, read adversarially while looking for a stacking-engine bug to fix; nothing
  found — recorded so the rotation doesn't re-tread it).** Four areas of the Current-focus §1 list traced **clean**
  on a close read: (1) `seestack/stack/accumulator.py` — the weighted-sum path's `_count` any-channel coverage, the
  min/max `k`-set insertion (the ±inf identities can never form an `inf − inf` because the `full` band requires
  `count ≥ 2k+1`, which fills every slot; the `single`/`lt3` degradation bands are disjoint and complete), and both
  Welford paths (`add_window`'s in-place view writes compute `new_mean` before overwriting `sub_mean`, so the
  M2 update reads the old mean, which is correct); (2) `seestack/stack/weighting.py` — every factor guards its own
  divisor, the geometric mean keeps the result inside `[min_weight, 1]`, and the empty-`weighted_list`
  `WeightingStats` positional construction is right; (3) `seestack/calibrate/apply.py` — the no-data pedestal
  masks, the wrong-shaped-bias gating (one predicate shared by the scaling path, the advisory warning *and* the
  provenance stamp) and the "returns a new array" contract on the empty-bundle path all hold; (4) the
  weight-vs-frame-count question in `seestack/bg/coverage_leveling.py`, which was the one thing that looked like a
  live bug from the outside — it is **not**: the leveler rounds the Σ-weight map to the nearest integer before
  `np.unique`, and says so, so quality weighting does not shatter it into a bin per pixel. The only real finding
  was the sidecar's mislabelled `BUNIT`, shipped this run as v0.250.1. **What is still worth a future adversarial
  pass:** `stacker.py` (2 400 lines — the κ-σ two-pass gating and the memory-budget drizzle-scale logic in
  particular) and `drizzle_path.py`, neither of which this run had the budget to read end to end.

### Measured observation (Builder 2026-08-06, v0.240.1 nudge) — from "Autonomy & friendliness"

- **MEASURED OBSERVATION (Builder 2026-08-06, measured while building the v0.240.1 nudge — file this before anyone
  "improves" the shoulder blind) — "Hold back highlights" rescues an *ordinary* blown core and is essentially
  powerless on an extreme one, because the Reinhard shoulder is asymptotic.** *(Image quality — PRIORITY 4; size M;
  **measured, deliberately NOT fixed**.)* `_highlight_rolloff` maps `[knee, +inf)` onto `[knee, 1)` with
  `t/(1+t)`, so nearly the whole output span is spent on the first few multiples of the 99.5th-percentile ceiling.
  **Measured** on synthetic S30-shaped scenes (compact core on a faint disk on a 1000 ADU sky, `autostretch`): a
  **60 000 ADU** core's internal gradient goes 8.1/255 → **13.4/255** at full protection with its blown fraction
  0.099 % → 0 — the knob works. A **400 000 ADU** core goes 0.12/255 → **0.62/255**: still under one 8-bit level,
  i.e. invisible, because after the shoulder the MTF's near-unity slope (`m/(1−m)` ≈ 0.11 at a typical STF midtone)
  shrinks what little separation survives. On a *wide* extreme core, protection can even make the flat patch
  slightly **larger** (measured 596 → 699 px at protect=1) as more of the bright range folds into the top band.
  This is the same wall v0.240.0's `_MIN_IMPROVEMENT` guard bumped into from the other side ("a frame so contrasty
  that the midtones transfer squashes the shoulder back together") — so nothing over-promises today: the suggester
  measures rather than assumes and simply stays silent there. **The real fix direction:** a *data-referred*
  shoulder (log-scaled to the frame's actual max rather than asymptotic) blended in as protection rises, so
  `protect=0` stays byte-for-byte the historical Reinhard. **Why it is filed and not built:** it changes pixels for
  anyone who has moved the slider or tapped "Core blown out", and how much extreme-HDR core a *real* Seestar OSC
  stack actually carries — versus a core that clipped in the sensor, where no shoulder helps — is exactly the
  real-data question this repo can't answer. Needs the owner's own M31/M42 stack to judge before shipping.

### Note (Builder 2026-08-05): "warn …" checked while shipping v0.236.0 — from "Autonomy & friendliness"

- **NOTE (Builder 2026-08-05, checked while shipping v0.236.0 — recorded so nobody re-treads it) — "warn about a
  mismatched dark at *pick* time" is ALREADY BUILT; the only thing left is a wording-drift risk.** The obvious
  follow-on to v0.236.0 looks like "say it before the night is spent, not after". It exists: `Stack.tsx` (~L357–405)
  already computes `darkExpMismatch` and a temperature warning from `GET /api/targets/{safe}/calibration-suggestions`
  (whose `params` carries the target's median `exposure_s` / `gain` / `sensor_temp_c` / modal dimensions) against the
  selected master's `MasterMeta`, and offers the "add a master bias to scale it" fix. The unattended binder is also
  gated — `_dark_match_confident` refuses a poor gain/temperature match and the caller applies the exposure gate
  separately. So v0.236.0 closed the genuinely open half (the user who picks a mismatched dark *anyway*, or whose
  saved default binds one, then never learns it hurt the picture). **The one real residue** is that the pick-time
  sentence in `Stack.tsx` and the after-the-fact sentence from `CalibrationMasters.calibration_warnings` are written
  independently, with independently-chosen thresholds (`expMismatch` in `calibrationFit.ts` vs
  `_EXPOSURE_MISMATCH_TOL` / `_TEMP_MISMATCH_TOL_C` in `calibrate/apply.py`) — so the app can warn before and go
  quiet after, or vice versa, on a borderline pair. ~~Worth one small pass to make the thresholds agree (and ideally
  serve one wording), *only* if someone is already in those files.~~ — **THRESHOLD HALF FIXED v0.237.1** (Builder
  2026-08-06, branch `claude/relaxed-turing-jox1fn`). The drift was real and one-directional: the form's rule was
  `|t_dark − t_subs| / t_subs > 0.25`, the engine's is `|t_subs / t_dark − 1| > 0.15` — both looser *and* anchored on
  a different exposure — so the engine is consistently the stricter of the two. **Reproduced by construction: a 30 s
  dark on 25 s subs** is 0.167 by the engine's measure (warned about on the finished run since v0.236.0) and 0.20 by
  the form's old measure against a 0.25 bar — silent at pick time. Same for a 10 s dark on 12 s subs, and the whole
  band between. Now there is one source of truth: `EXPOSURE_MISMATCH_TOL` / `TEMP_MISMATCH_TOL_C` are public in
  `seestack/calibrate/apply.py` (the private names stay as aliases), `…/calibration-suggestions` serves them in an
  additive `tolerances` block, and the form's cautions run through two pure helpers in `calibrationFit.ts`
  (`exposureMismatch` / `tempMismatch`) that prefer the served numbers and fall back to mirrored constants for an
  older backend. Both are one-sided like the size check — an unknown or non-positive exposure (a bias master records
  0 s) never warns. The temperature thresholds already agreed at 5 °C; that literal is no longer duplicated in
  `Stack.tsx`. Upgrade-safe: additive response key, no config/DB/on-disk change, no stacking behaviour touched —
  only which advisory sentences appear, and strictly toward "warn about the pairs the run will complain about".
  **Tests (+13):** `calibrationFit.test.ts` (+8 — the borderline pair, a matched pair inside the slack, the
  master-anchored denominator, the one-sided guards, and the served-tolerance preference with its fallback for a
  null/zero/negative/NaN/absent block), `Stack.test.tsx` (+1 — the 30 s-dark-on-25 s-subs pick now warns) and
  `tests/webapp/test_calibration.py` (+1 pinning that the served values *are* the engine's constants, so a future
  sensitivity change can't leave the form behind). **Still open (the smaller half):** the two *sentences* are still
  written independently, so the wording can drift even though the trigger can't. (S, friendliness — PRIORITY 3.)

### Note (Builder 2026-08-05): the 3-frame-default-stack idea's placement — from "Autonomy & friendliness"

- **NOTE (Builder 2026-08-05) — the "a 3-frame default stack gets no outlier rejection" idea (filed under Image
  quality, Scout 2026-07-23) is largely moot for the *beginner* path; check before spending a run on it.** Verified
  this run: the beginner never reaches the bare engine default. `webapp/routers/stack.py:168` does
  `merged.setdefault("auto_reject", True)` for a never-configured Stack form, and `webapp/pipeline.py:~2087` sets
  `auto_reject=True` whenever the merged options carry no explicit rejection preference — and `auto_reject`
  resolves to **min/max** below `_auto_kappa_min_frames(κ)` (n < 11 at the default κ=3), which is exactly the
  rejection a 3-frame stack can use. So a walk-away / one-click 3-frame stack already drops the lone trail. The
  residual gap is only a user who *explicitly* chose κ-σ and then stacked 3 frames — a deliberate choice, and
  changing it is the default-behaviour flip the original entry already flagged. Recommend leaving it closed unless
  the owner asks.

### Dogfood baselines at v0.351.0, v0.345.7 and v0.345.2 (the third, fourth and fifth measurements) — from "Friendliness"; AGENTS.md §1 now points here

- **⚪ DOGFOOD BASELINE (Builder 2026-09-04, `scripts/agent-dogfood.sh` at v0.351.0 — the FIFTH measurement,
  and the fifth that says DO NOT open a speculative IA slice).** Full run (boot → sample → stack → Playwright
  probe at 1440 px and 420 px): **nothing overflowing, no console errors**. Tallest pages are **identical to
  the v0.345.7 measurement, to the pixel** — phone Target 3,014 px, `/life-list` 3,008 px, the editor
  2,815 px, then desktop Target 2,010 px, desktop editor 1,841 px, Dashboard 1,785 px (phone), `/stack`
  1,748 px (phone), `/life-list` 1,453 px (desktop). Five measurements across ~130 versions and the worst page
  has moved 21 px: the IA work is done, and the standing rule (put a new feature *inside* the existing
  grouping) is what is left of that priority.
  **What this pass found is the picture card's 40 % black letterbox** (shipped as v0.351.1, below) — and the
  way it found it is the part worth keeping. The screenshot had already been looked at twice by earlier runs,
  which both read the black as *uncovered canvas* and filed/declined a caption for it. Asking the **app**
  instead of the screenshot — `GET .../preview` (480×320, three dark columns) and `GET .../stack-health`
  ("even coverage") — showed it was the card's own box. So the probe's speciality is not only "two correct
  lines that contradict each other" (three passes running): it is anything where the *composite* on screen is
  read as data. **Confirm what a pixel is with an endpoint before writing copy that explains it.**


- **⚪ DOGFOOD BASELINE (Builder 2026-09-04, `scripts/agent-dogfood.sh` at v0.345.7 — the fourth measurement,
  and the fourth that says DO NOT open a speculative IA slice).** Full run (boot → sample → stack → Playwright
  probe at 1440 px and 420 px): **nothing overflowing, no console errors**. Tallest pages, phone first:
  the Target page **3,014 px** (unchanged across four measurements and ~100 versions), `/life-list` 3,008 px,
  the editor 2,815 px, then desktop Target 2,010 px, desktop editor 1,841 px, Dashboard 1,785 px (phone),
  `/stack` 1,748 px (phone), `/life-list` 1,453 px (desktop). **What this pass found is the entry below** —
  the two standout cards on "Your sky, so far" naming one target twice — which no code read had caught in the
  ~30 versions since the page was last edited, because each card is right on its own and only the rendered
  row shows the same picture beside itself. That is now three consecutive dogfood passes where the *finding*
  was a duplication or a contradiction between two lines that are individually correct: worth treating as the
  probe's speciality when choosing what to look at in the screenshots.

- **⚪ DOGFOOD BASELINE (Builder 2026-09-04, `scripts/agent-dogfood.sh` at v0.345.2 — the third measurement in
  a row that says DO NOT open a speculative IA slice).** Full run (boot → sample → stack → Playwright probe at
  1440 px and 420 px): **nothing overflowing, no console errors**, and the tallest page is still the Target
  page at **3,014 px on a phone** — the *same* number the v0.338.1 probe recorded, against 14,584 px on the
  worst page before the 08-13→16 slices. The rest, tallest first: `/life-list` 3,008 px (phone), the editor
  2,829 px (phone), the Target page 2,010 px (desktop), the editor 1,805 px (desktop), the Dashboard 1,785 px
  (phone), `/stack` 1,748 px (phone), `/life-list` 1,453 px (desktop). **So the standing IA banner in
  AGENTS.md §1 keeps its verdict**: three measurements across ~90 versions agree that nothing is stacked
  badly and the worst page has not moved. Re-measure before any future slice; do not open one on a reading of
  a route file.
  **What the pass *did* find is the entry directly above under "Editor"** — the export panel's trailing
  paragraph, which is invisible to a code read (each of its sentences is defensible on its own; only the
  rendered page shows five grey paragraphs in a row) and is exactly the kind of thing the running-app probe
  exists to catch. Shipped as v0.345.3.

### Declined once: "already answered" (Builder 2026-09-04) — from "Friendliness"

- **⚪ DID THE GREP, AND THE ANSWER IS "ALREADY ANSWERED" — DECLINED ONCE so it isn't re-litigated (Builder
  2026-09-04).** The entry below asks for a caption under the Target picture explaining the canvas's black
  margins, and tells whoever picks it up to grep first and decline it as copy churn if the app already says
  it where the beginner is looking. It does. `seestack/stackhealth.py` (~line 467, `kind="coverage"`) already
  emits, into the "How's my stack?" panel on the *same page*: *"About N% of this picture has far fewer frames
  than the best-covered part, so it's noisier and uneven there. Trim border gives a clean, even rectangle."*
  — with `action="trim_border"`, i.e. it also names the one-click fix, which a bare caption would not. It is
  measured (`coverage_thin_frac`) rather than guessed, and it self-hides below `_COVERAGE_THIN_SHARE` so an
  evenly-covered stack is never told about a border it hasn't got. **The one honest gap, recorded rather than
  built:** the wording is about *noise* ("noisier and uneven"), not about *black* — a beginner staring at a
  flat black band may not connect the two. ~~If anyone ever wants to close that, it is **four words inside the
  existing sentence**, not a new caption or card: say the thin edge *looks dark*. Do not add a second surface
  for it.~~ — **⚪ THE FOUR WORDS ARE THE WRONG WORDS; DECLINED WITH THE MEASUREMENT SO NOBODY SHIPS THEM
  (Builder 2026-09-07).** Sized it, went to the statistic behind the note first — the lesson the entry
  directly below this one exists to teach — and the copy would have been **false**. The note fires on
  `run.coverage_thin_frac`, i.e. `stacker.coverage_thin_fraction`, whose docstring and code both say it
  **excludes uncovered pixels**: `thin = count((cov > 0) & (cov < 0.25 * peak))` over
  `n_covered = count(cov > 0)`. The black band a beginner is staring at is `cov == 0` — NaN, "no coverage",
  rendered black — and it is in **neither** term of that ratio's numerator. Probed directly, holding the thin
  fringe fixed at 500 px and growing the black region: the thin count stays **500** at 0, 20, 40 and 60 black
  rows, while the reported share moves **0.0500 → 0.0625 → 0.0833 → 0.1250** purely because the *covered*
  denominator shrinks. So the pixels this note counts are thin-**but-covered** — the same brightness as the
  rest of the picture, just noisier — and telling the owner they "look dark" would explain the one part of
  their picture this measurement is blind to. **Its wording is already right for what it measures.** If the
  black is ever worth a sentence it needs its own measured quantity (an uncovered share, which nothing
  records today), not a rewording of this one — and the entry directly below records that the wide black
  bands seen on the sample were `AnnotatedImage` letterboxing, not canvas at all. Leave the sentence alone.
  **▶ THE QUANTITY NOW EXISTS, AND THE SENTENCE IS ITS OWN — SHIPPED v0.377.0 (Builder 2026-09-07). Closed;
  do not re-open either half.** `stacker.uncovered_fraction` measures the share of *every* canvas pixel no
  frame reached, `stack_runs.uncovered_frac` persists it (no `SCHEMA_VERSION` bump —
  `_reconcile_table_columns`, so a rollback still opens the project),
  `coverage_backfill.backfill_coverage_shares` heals old runs off the map they already wrote, and
  `stackhealth`'s new `uncovered` note says what the black is in its own words with its own number. The thin
  note's sentence is **unchanged**, exactly as this entry demanded. The measurements that set the new floor
  (`_UNCOVERED_SHARE = 0.12`) are in [`SHIPPED.md`](SHIPPED.md) — including the row that proves this entry's
  point: a diagonal two-panel mosaic reads **36.6 % uncovered and 0.00 % thin**.

### Closed: the premise was wrong, measuring showed it (Builder 2026-09-04) — from "Friendliness"

- **⚪ CLOSED — THE PREMISE WAS WRONG, AND MEASURING IT IS WHAT SHOWED THAT (Builder 2026-09-04). The black
  was the *card*, not the canvas; see the shipped entry above (v0.351.1).** Probed on the running app rather
  than read off the screenshot again: the sample's stored preview is 480×320 with **three** near-black
  columns, and `stack-health` on that run answers *"even coverage"*, correctly. The wide bands were
  `AnnotatedImage`'s full-width fixed-height box letterboxing a 1.5:1 picture into a 2.5:1 slot. **So the
  caption this entry asks for would have been actively wrong** — it would have told the owner the dark edges
  were thin coverage when they were empty card. Both this entry and the declination above it argued about
  *which surface* should explain the black without either checking that there was any black in the picture.
  **The lesson worth keeping: a screenshot shows you the composite. Before writing copy that explains a
  pixel, ask the app what that pixel is.** Original entry follows, struck.

  - ~~**NEW IDEA (Builder 2026-09-04, seen on the Target page in the same dogfood pass — GREP FIRST, this may be
    answered already) — the picture card shows the canvas's black margins with nothing saying what they are.**~~
    *(Pillar: friendliness — PRIORITY 3; size XS if it is only a caption; confidence: **observed on the sample,
    not traced** — the sample is one field, so a real mosaic may read differently.)* "Your picture" on the
    Target page rendered the stack with a wide black band down each side: the union canvas is wider than the
    sky every frame covered, which is correct and is exactly what `auto_crop_border` trims when Auto runs in
    the editor. A beginner meeting it on the *unedited* stack has no way to know whether their picture is
    broken, and the caption underneath talks about frames and exposure rather than about the black. **Shape:**
    one conditional line under the picture when the run's coverage says a meaningful border is uncovered —
    *"the dark edges are where fewer frames overlapped; Auto trims them when you edit"* — reusing
    `_trim_rect_for_run` / the existing trim fraction rather than measuring anything new. **Grep first:** the
    editor already surfaces "% of ragged mosaic edge to trim" in its Auto note and the Target page already
    carries a coverage-thin verdict in "How's my stack?" — if either already answers this where the beginner is
    looking, this is copy churn and should be declined.

### Dogfood finding, low value (recorded, not fixed) — from "Friendliness"

- **DOGFOOD FINDING, LOW VALUE — recorded so it is not re-found, not because it should be fixed (Builder
  2026-09-01).** The **Library**'s target card truncates a long name (*"Sample: Orion Nebula (…"*) where the
  Gallery's, since v0.322.4, does not. Measured on the running app: it is **desktop-only** — at 1440 px the
  grid gives ~280 px cards and `Library.tsx:101`'s `truncate` bites, while at 420 px the card is full-width and
  the whole name fits. That is the opposite of the v0.322.4 Gallery finding, whose severity came precisely from
  a phone having no hover to recover the name; here the one width that truncates is the one width where the
  `title=` tooltip works. **If it is ever touched**, the shape is `lineClamp={2}` with `align="flex-start"` on
  the `Group`, which lets the name use a second line while the chevron stays pinned to the first — the existing
  comment on that row explains why the chevron must not wrap, and that constraint survives. Not worth a run on
  its own.

### Process note (Builder 2026-09-01): the 32-error non-regression — from "Friendliness"

- **⚠️ PROCESS NOTE (Builder 2026-09-01, after it briefly looked like a 32-error regression) — don't run the
  Python suite and a `vite build` at the same time.** The webapp serves the SPA out of `webapp/static`, which
  `npx vite build` **deletes and rewrites**; a pytest run overlapping it reported `3792 passed, 32 errors`
  where the same tree, run alone, gives the baseline `3824 passed, 2 skipped`. The errors land in
  `tests/webapp/*` and look like real fixture failures, not like an I/O race, so the temptation is to go
  hunting. **Both halves of the trap are worth knowing:** `scripts/agent-dogfood.sh` runs a `vite build` of its
  own (always with `--build`, and automatically when `webapp/static/index.html` is missing), so "just the
  dogfood pass" counts as a concurrent build. Serialise them, and re-run alone before believing any webapp
  error you didn't cause.

### Class swept: two sites fixed in v0.322.4 — from "Friendliness"

- **⚪ CLASS SWEPT — two sites, both fixed in v0.322.4; recorded so nobody re-sweeps it (Builder 2026-09-01).**
  The construct: a card header where a `truncate`d name and a badge group share one `wrap="nowrap"` row and the
  badge group carries `flexShrink: 0`. The badges then take the width they want and the **name** absorbs every
  pixel of the squeeze — which is backwards, because the name is the identifier and the badges are the
  decoration. Grepped `flexShrink: 0` across `frontend/src` and read every hit that sits beside a truncating
  name. **Every other hit is on the right side of the line:** `Library.tsx`'s target card already puts the name
  on its own row with the badges below (that is the shape v0.322.4 adopted, so the browse surfaces now agree),
  and its `flexShrink: 0` is on a **chevron icon**, which is 16 px and must not shrink; the Gallery's
  video-still card pairs a label with a *single* small badge, which cannot squeeze a name to nothing. **The
  generative test for new code, since it costs nothing at review time:** if a name and a badge group share a
  no-wrap row, ask what the row does when the name is long — if the answer is "the name disappears", the badges
  belong on their own line.

### Recorded so it isn't re-investigated (Builder 2026-08-17, /tonight phone screenshot) — from "Friendliness"

- **RECORDED SO IT ISN'T RE-INVESTIGATED (Builder 2026-08-17, seen on the phone screenshot of `/tonight`) — the
  Night picker prints `mm/dd/2026`, which looks like the US date order the rest of the app deliberately avoids,
  but it is NOT ours to fix.** The Tonight page's Night field is a native `<input type="date">`; its placeholder
  and displayed order come from the *browser's* locale, not from the app (the probe's Chromium runs `en-US`). The
  value it submits is always ISO `YYYY-MM-DD`, and every date the app *renders* already goes through
  `formatStampDate` (fixed in v0.264.2). Changing the visible order would mean replacing the native picker with a
  custom one — losing the phone's own date wheel, which is the better control on the device the owner uses. So:
  **not a bug, don't "fix" it**; if it ever matters, the honest change is a `lang`/locale hint, not a new widget.

### Declined once: no "Finish it" button (Builder 2026-08-16) — from "Friendliness"

- **DECLINED ONCE, recorded so it isn't re-litigated (Builder 2026-08-16) — do NOT add a "Finish it" button next to
  the `edit not exported` label on the History and Gallery cards.** *(Considered while shipping v0.262.1.)* The
  one-click finish exists on the Target page's hero (`LatestPictureCard`), which covers the case that actually
  happens: you edited your *newest* picture, saved, and closed. On an *older* run the realistic next step is to
  reopen the editor and look at it again, not to export it blind — and the badge row on both cards is exactly the
  clutter the IA overhaul is trying to reduce, so paying a button there for a rare action is the wrong trade. The
  label stays what it is: honest, and one click from the editor via the card it sits on.

### Measured: the drizzle path is not bit-reproducible under multithreading (do not serialise it) — from "Image quality"

- **⚪ MEASURED, RECORDED SO NOBODY RE-TREADS IT — the **drizzle** path is not bit-reproducible under
  multithreading; every other combine is. Not a picture bug at the size measured; do NOT "fix" it by
  serialising the accumulation.** *(Builder 2026-09-04, found while proving the combine-dispatcher routing
  changed no pixels — it was the one case of six whose hash moved, and it moves on `origin/main` too.
  Pillar: trust / image quality — PRIORITY 4. Confidence: **measured**, four runs, both trees.)*

  **What was measured.** Sixteen synthetic Seestar subs (one carrying a planted satellite trail), stacked
  twice with identical options — `drizzle`, `drizzle_reject`, `drizzle_scale=1.5`, `max_workers=2` — produce
  masters that differ. Repeated four times against the same first run:

  | pair | max abs diff | pixels > 1 ADU | pixels differing at all |
  |---|---|---|---|
  | run0 vs run1 | 7.24 | 12 | 563,725 / 1,036,800 |
  | run0 vs run2 | **117.66** | 12 | 491,361 / 1,036,800 |
  | run0 vs run3 | 7.24 | 12 | 392,844 / 1,036,800 |

  No NaN ever swapped sides (`nan_mismatch = 0`), so coverage is stable — it is the *values* that move.

  **The size, in context, which is why this is filed rather than fixed.** The half-a-million differing
  pixels are float-order noise: sub-0.01 ADU on an image whose median is 5.7. Only **12 pixels of a million**
  move by more than 1 ADU, and the 117 is a **star core** — 8,817.96 against 8,753.12, i.e. **0.7 % of the
  value**, on a pixel where a κ-σ clip decision flipped on a steep gradient. Nothing structural, nothing
  visible, and nothing that changes what the picture shows.

  **The cause, and the reason serialising is the wrong cure.** Isolated by probe:
  `max_workers=1` is **bit-identical** (`ndiff = 0`); `max_workers=2` diverges **with and without**
  `drizzle_reject` (max 0.0117 and 0.0098 on the runs that did not catch a clip flip). So it is
  non-associative float addition into a shared canvas under two workers — not the rejection pass, which
  only *amplifies* it at a handful of pixels. The κ-σ and min/max paths are deterministic at
  `max_workers=2` (`ndiff = 0`), because their consumers accumulate in submission order. Forcing the same
  on drizzle means giving up the parallelism on the path that needs it most (the owner's mosaics are the
  largest canvases this app builds), to buy a reproducibility nobody has asked for.

  **What it *does* mean, and the only thing worth acting on.** A re-stack of the same subs is not
  guaranteed to be byte-identical, so **no test or tool may assert a drizzled master's bytes** — compare
  with a tolerance, or compare a non-drizzle case. The six-case before/after script that found this is the
  method to reuse for any future hot-path refactor; run it with `max_workers=1` if a drizzle case must be
  hashed.

### Answered and closed, measured and dated, no constant changes (Builder 2026-09-03) — from "Image quality"

- **⚪ ANSWERED AND CLOSED — MEASURED AND DATED, NO CONSTANT CHANGES (Builder 2026-09-03, branch
  `claude/sweet-babbage-861nhx`). Read this before re-opening it; the whole point is that nobody should
  blind-flip an on-by-default constant on the strength of the lead's premise.** *(No code change wanted.)*
  The lead below asks which shipped constants were *tuned by eye through a curve that moved the sky* — Auto's
  contrast curve brightened a sky-dominated background by 6–33 % until v0.326.1. It names three in
  `auto_recipe`, in order of suspicion: `target_bg`, then the saturation scaling, then the SCNR amount. **All
  three predate the curve, so none of them was ever judged through it.**

  | constant | introduced | vs. the auto curve entering Auto |
  |---|---|---|
  | `target_bg = clip(0.24 − sky×0.4, 0.14, 0.24)` | `21796d65`, **2026-06-14** | 20 days before |
  | `saturation = clip(1.25 − sky_sigma×6, 1.05, 1.25)` | `5369c479`, **2026-07-03** | 1 day before |
  | `tone.scnr amount 0.7` | `c7351d76`, **2026-07-03** | 1 day before |
  | `tone.curves {auto: True}` in `auto_recipe` | `70fa0138`, **2026-07-04** | — |

  All three carry byte-identical values at `70fa0138` and today, so none was re-tuned in the window either.
  The lead's fourth candidate — the built-in presets' `0.18 / 0.22 / 0.25` — is a **wrong premise**, and it is
  the one most likely to send a future run at a live default: those presets ship **fixed-point** curves
  (`tone.curves {points: […]}`), never `auto: True`, and A1 lived only in the data-driven
  `suggest_tone_curve`/`_sky_mode` path. Their curves *do* move the sky (galaxy_broadband's `0.25→0.20` pulls
  a 0.18 background down), but they were chosen in the same commit as their `target_bg`, tuned together, and
  A1 never touched them. So "the 0.15–0.22 band and the 0.25 preset were pushed in opposite directions" is
  true of the *auto* curve's arithmetic and simply does not apply to the presets.

  **The lead also asks for the delta re-measured on v0.326.1+, so here it is**, per op, on a realistic linear
  OSC scene (sky pedestal + broad object + 220 stars + a mild OSC green cast), background read as the median
  of a star-free corner strip rather than a histogram mode:

  | after | background |
  |---|---|
  | `tone.stretch` (`target_bg` 0.2305) | 0.2135 |
  | `tone.scnr` | 0.2135 |
  | `tone.saturation` | 0.2135 |
  | **`tone.curves` (auto)** | **0.2139 — +0.2 %** |
  | `detail.sharpen` | 0.2135 |

  **The curve now moves the finished background by two parts in a thousand**, i.e. it is on the identity as
  designed, which is exactly the condition `target_bg` was chosen under three weeks before the curve existed.
  Nothing to re-tune. *(A measurement trap worth keeping: reading the same background as a histogram **mode**
  instead makes `detail.sharpen` look like a −6.5 % darkening. It isn't — sharpening widens the histogram and
  moves the winning bin. Two estimators, one true answer; use the corner median.)*

  **One incidental measurement, recorded so nobody re-derives it and nobody "fixes" it:** `a["sky"]` is the
  median of the **whole-image-normalised** luminance (`[p0.5, p99.5] → [0, 1]`), so it is deliberately blind
  to the linear pedestal — `target_bg` read 0.2305 for every sky from 0.005 to 0.15 on the fixture above, a
  30× range. The knob is not inert, it just responds to how *object-dominated* the frame is rather than how
  bright the sky is in ADU (0.2314 / 0.2305 / 0.2330 across faint / typical / large-object scenes). Real
  deep-sky stacks therefore sit around 0.21–0.24 and never approach the 0.14 floor. **That is the design, not
  a bug** — do not "restore" the pedestal sensitivity.

  *(The original lead follows, for the record — this is answered.)*

  - **LEAD (Builder 2026-09-02, the half of A1's last line nobody has done — distinct from the sweep idea below,
    and worth keeping separate) — every constant that was *tuned by eye* through the old contrast curve was
    tuned through a curve that moved the sky, so re-measure the ones that decided a default.** *(Pillar: trust +
    image quality — PRIORITY 4; size M; pure measurement, no behaviour change unless a number turns out wrong.)*
    The ⭐ entry below asks "which other *statistics* share A1's clipped-shadow blindness?"; this asks the
    narrower, more concrete question **"which shipped *constants* were chosen by looking at a picture the bug had
    already altered?"** Until v0.326.1 Auto ended with a curve that brightened a sky-dominated stack's background
    by **6–33 %** at `target_bg` 0.15–0.22 and *darkened* it ~20 % at 0.25, so any past A/B judged on a finished
    Auto picture was reading a background Auto had moved. **Where to look, in the order they matter:** the
    `target_bg` choices themselves (`tone.stretch` 0.18 in `auto_recipe` vs 0.18/0.22/0.25 in the built-in
    presets — picked to look right *through* the old curve, and the most likely real finding, since the
    0.15–0.22 band and the 0.25 preset were being pushed in **opposite** directions); then the SCNR amount and
    the saturation scaling in `auto_recipe` (both chosen relative to measured sky/noise and both applied *before*
    the curve, so probably safe — confirm rather than assume); then any Shipped entry whose evidence is a
    before/after sky or brightness number measured on a finished Auto picture. **Method:** re-run the comparison
    on v0.326.1+ and report the delta; change a constant only if the old choice is *measurably* worse now, and
    say so with the numbers. **Caution:** these are on-by-default constants on a live install — a change alters
    every future picture, so it wants its own commit and a stated before/after, never a fold-in.

### Process note: the sixth concurrent-duplicate collision (Builder 2026-08-30) — from "Image quality"

- **⚠️ PROCESS NOTE — THE SIXTH CONCURRENT-DUPLICATE COLLISION (Builder 2026-08-30, branch
  `claude/compassionate-galileo-ezix3s`) — two Builders swept this same QA lead in the same hour and both
  fixed `transparency_trend`.** Their fix (v0.304.1, above) landed on `main` first, so **mine was stood down
  wholesale at merge time** and `main`'s implementation is the one that ships — the two were functionally
  equivalent (level each panel onto the session's overall median behind the `pointing_groups` gate; theirs
  calls the field `n_pointings`, mine called it `n_panels_levelled`). **Nothing was salvaged from the
  duplicate half and nothing needed to be.**
  **What the collision did NOT cost, and why:** the same sweep, in the same run, also turned up **two sites
  the other Builder did not touch** — the per-run `transparency_ratio` behind the "Hazy night" badge
  (v0.304.2) and the bulk "reject worst N%" cut (v0.304.3), both below. Working the lead's *whole* candidate
  list rather than stopping at the first hit is what made the run still worth its hour.
  **The lesson, on top of the five notes above:** claiming early did not help here — both runs claimed within
  minutes of each other, and a claim is only visible after it is *pushed and fetched*. For a **QA lead** that
  names several candidate sites, the cheap defence is to say in the claim **which site** you are taking, and
  to re-fetch `main` before writing the fix for a site whose name is already in another agent's claim.

### Measured ground truth (Builder 2026-07-30 engine QA probe) — from "Image quality"

- **MEASURED GROUND TRUTH (Builder 2026-07-30, engine QA probe — no code change needed; recorded so no future
  run re-derives it).** Ran the real `run_stack` end-to-end on synthetic 8-sub Seestar sets (480×320, shared
  stars, independent per-sub noise) to check what the rejection modes actually do to the *final image*:
  **(1) noise really does drop as √N** — a single frame's sky σ 33.5 ADU → 11.80 with a plain mean and
  **identically** 11.80 with κ-σ (κ=3), i.e. **2.84×** against the ideal 2.83×, so the accumulator +
  per-frame flatten chain is unbiased. **(2) The κ-σ blind spot is real and large on the final picture.**
  With a bright trail planted in **one** of the 8 subs, the trail ridge lands at **+502 ADU** above sky on
  *both* the plain-mean and the κ-**σ** stack — byte-identical results, because a lone point's z-score against
  statistics that include it caps at `(n−1)/√n = 2.47 < κ`, exactly as `_auto_kappa_min_frames` documents.
  `min_max_reject` (k=1) cuts the same ridge to **+8.3 ADU**. So the "κ-σ can't see a lone trail below ~11
  subs" claim is not theoretical — it is a ~60× difference in the delivered image. **(3) The k>1 trim costs
  real SNR on a thin stack:** at 8 frames, min/max k=1 gives a 2.73× noise reduction and **k=3 only 2.45×**
  (it throws away 6 of 8 samples per pixel), so raising the count on a short session measurably degrades the
  background — the Stack form's existing `minMaxKTooHighHint` is earning its keep. **Coverage check (why this
  is ground truth, not a bug):** every path a beginner actually takes already turns `auto_reject` on — the
  walk-away chains (`webapp/pipeline.py`, `auto=True`, when no explicit rejection key is set) and the Stack
  form for a never-configured target (`webapp/routers/stack.py`, `merged.setdefault("auto_reject", True)`) —
  and it resolves to min/max below 11 subs. The residual exposure is a user who once saved per-target/global
  stack defaults *without* a rejection key and then stacks a short session: they keep plain κ-σ and the trail
  survives. That's narrow and self-inflicted, and flipping the dataclass default is a §9 default change — so
  it stays an observation, not a fix. (Repro: `tests/synth.py::make_star_field(streak=True)` in 1 of 8 subs,
  same WCS, sample the ridge `y=60..260, x=y−10` in the green plane.)

### Measured non-bug: SCNR's noise-protection sigma — from "Image quality"

- **MEASURED NON-BUG — don't "fix" SCNR's noise-protection sigma to use `ctx.scaled_px` (Builder 2026-07-30, spotted
  and measured while shipping the colour-blotch smoother v0.220.0).** `_scnr`'s noise-protected estimator smooths
  green and the R/B neutral with a **fixed** `_SCNR_NOISE_SIGMA = 3.0` px (`seestack/edit/ops/tone.py`), unlike every
  other spatial editor knob (sharpen radius, bilateral extent, deconv PSF, and now the chroma radius), which is
  scaled by `ctx.scaled_px` for preview↔export parity. That asymmetry looks like a parity bug and isn't — **it is the
  better of the two**, because the proxy is *stride*-decimated (`edit/proxy.py`), so a proxy pixel carries the same
  per-pixel noise as a full-res one and the estimator's bias depends on how many *samples* the kernel averages, not
  what physical area it spans. Measured on a realistic 1080×1920 stretched sky (400 stars, real broad green
  structure, σ 0.03) against a ×3 stride proxy, comparing each proxy render to the *decimated export*: the shipped
  fixed 3 px gives **mean-abs green difference 0.0019 (1.06 % of sky) with zero mean bias**, while scaling the sigma
  to 1 px gives **0.0039 (2.17 %) with a −0.12 % green bias** — i.e. scaling would roughly *double* the
  preview↔export mismatch and reintroduce part of the magenta bias v0.210.5 removed. Leave it alone; if it's ever
  revisited, the honest shape is `max(floor, scaled)` with a floor high enough to still cancel noise, and it needs a
  measurement, not a one-line flip. Confidence: measured. (No action — filed so a future audit doesn't re-chase it.)

### Observation (Builder 2026-07-30): the per-frame object mask, measured — from "Image quality"

- **NEW OBSERVATION (Builder 2026-07-30, measured while unstarving the per-frame object mask, v0.213.0) — the
  per-frame flatten still absorbs ~55 % of a nebula that fills most of the frame, and nothing tells the user.**
  *(Image-quality + friendliness; size S for the nudge, M for a real fix; PRIORITY 3–4.)* Measured on a synthetic
  M42-shaped scene (a bright nebula spanning ~80 % of a 540×960 frame, 12 % LP gradient): the nebula keeps
  **41.6/44.0/42.2 %** of its R/G/B amplitude through `subtract_background` — *ratios intact, so no colour damage*,
  but a lot of flux gone. The pre-v0.213.0 mask kept 47.1/46.7/47.6 %, i.e. this is a pre-existing limitation of
  fitting a 128 px mesh through a frame-filling object, not something the mask fix introduced (it moved the number by
  5 points while removing the gradient starvation that was far more damaging). `bg/per_frame.py`'s own module
  docstring already names the situation and the remedy — *"if the nebula fills more than ~half the frame … turn bg
  flatten OFF (`mode='off'`) and remove residual gradients on the final stack instead"* — but a beginner will never
  read that, and nothing in the app detects it. **Two shapes, both cheap:** (a) *detect and say so* — the object mask
  now knows how much of the frame is structure, so a stack whose per-frame masks routinely cover most of the frame
  could stamp a plain-language note on the run ("this target fills the frame — AstroStack turned per-frame flattening
  down so it wouldn't eat the nebula"); (b) *act on it* — auto-fall-back to `mode='off'` (leaving the final gradient
  pass to do the work) when the mask covers more than ~half the frame for most subs. (b) changes stacking behaviour,
  so it needs a measurement harness and probably owner sign-off; (a) is additive and safe. Confidence: measured.

### Observation (Builder 2026-07-30): a mesh-scale sky feature (amp glow) — from "Image quality"

- **NEW OBSERVATION (Builder 2026-07-30, same run) — a genuinely mesh-scale sky feature (amp glow in a corner) is
  partly masked as "object" by the block-averaged extended pass, so ~⅓ of it survives the flatten.**
  *(Image-quality; size S–M; PRIORITY 4.)* Measured by adding a sharp exponential corner glow (150 ADU peak, not
  representable by the deg-2 detrend) to a realistic sub: the mask covers 60.6 % of the glow corner vs 3.1 % of the
  far corner, and after `subtract_background` the corner sky sits at **+50 ADU** instead of ~0. **Not a regression** —
  the pre-v0.213.0 mask left +52 ADU on the same scene (and, with a gradient present, left the *opposite* corner at
  +57 ADU where the new mask leaves +9) — but it is the known cost of the `_EXT_NOISE_FLOOR = 0.5·σ` floor on the
  extended pass: anything smooth, bright and above half a sub's sigma reads as structure. **Fix direction if it ever
  matters:** the discriminator is that amp glow is *fixed to the sensor* while a nebula is fixed to the sky, so it is
  visible as the part of the extended mask that does not move with dither across a session — i.e. a stack-level
  (not per-sub) determination, which is also how a real defect/glow map would be built (see the persistent
  defect-map idea below). Only worth doing if a real Seestar sub shows meaningful amp glow. Confidence: measured.

### Measured, recorded (Builder 2026-09-04, the year-hero) — from "Features"

- **⚪ MEASURED, RECORDED SO NOBODY RE-INVESTIGATES (Builder 2026-09-04, hit while writing the year-hero
  tests) — the night-fold cache can serve a stale year/heatmap for up to 120 s after a frame's *timestamp*
  changes without moving its target's `last_activity_utc`.** *(No code change wanted — bounded, pre-existing,
  and the cheap alternatives are worse.)* `_cached_night_acc`'s signature is
  `(lon, [(safe_name, last_activity_utc)])` over the registry. Re-dating an *existing* frame (a header
  re-read, a hand edit, a re-ingest that lands an older stamp) can leave the registry row untouched, so the
  signature matches and the fold is reused until `_ACTIVITY_CACHE_TTL_S` (120 s) expires — the Dashboard
  heatmap, the year recap and the recap poster all then quote the pre-edit nights. **Why it is not worth
  fixing:** the only signature that would catch it is one over the frames themselves, which is the library
  walk the cache exists to avoid, and every *ordinary* path that changes a frame's night (ingest, a scan)
  moves `last_activity_utc` with it. 120 s is a bounded, self-healing wrong answer on a surface nobody is
  watching second-by-second. **What this costs a test author, which is the actual reason to record it:** a
  test that mutates a timestamp *between* two requests to any night-shaped endpoint will silently read the
  first request's fold. Arrange the whole fixture before the first request instead — that is why
  `test_year_hero_says_so_when_its_picture_may_carry_another_years_light` builds both years up front.

### Collision process notes four through ten (Builders 2026-08-29 → 2026-09-02) — from "Features"

- **⚠️ PROCESS NOTE + PROPOSAL (Builder 2026-09-02) — collision TEN, and it was a *clean sweep*: two Builders
  in one hour independently built the **same three items**, and every one of them was the top open entry of
  its section.** Not one item overlapped by chance — the asinh preview-parity bug (top of "Bugs"), the
  bootstrap centre bug (second in "Bugs"), and "Plan my week" (top of "Features that serve real workflows").
  Both runs converged so hard that we independently chose the same helper *names* (`AsinhStats`,
  `_preview_grid_asinh_stats`, `wcs_image_center_deg_from_text`) and the same extraction
  (`_iter_night_dark_windows` / `upcoming_dark_windows`). The other run landed first; mine was dropped.

  **The claim-by-site discipline cannot fix this, and notes six through nine have now established that
  empirically.** Claiming is a *publication*, and both agents publish after they have already chosen — the
  choice happens in the first thirty seconds of a run, from a file that tells both of them the same thing.
  Fetching again between tasks catches a collision only when the other agent finished a task first; it never
  catches two agents starting together, which is the common case when runs are scheduled on the same hour.

  **The proposal, and it needs no coordination mechanism at all: stop making every Builder pick the top
  item.** Have each run pick **uniformly at random from the top ~4 open, unclaimed entries** of the
  highest-priority section that has any (still never below a section that has open work — the priority bands
  are unchanged, only the tie-break within one). Two independent runs then collide with probability ~1/4
  instead of ~1, the expected wait for the true top item goes from "always first" to "within a couple of
  runs", and *nothing* is lost: every one of those four is work the backlog already says is worth doing next.
  A cheap refinement if the top item is genuinely urgent — mark it `⭐` and make ⭐ items always-first, which
  the file's own convention already supports and which the current queue happens not to use.

  This belongs in **AGENTS.md §3** (the decision rule), not just here, since it changes how every run chooses;
  filed rather than edited because §3 is the owner's manual and this is a real behaviour change to every
  agent. **Cost of not doing it:** this hour, two of two Builder runs produced almost entirely duplicate work.

- **⚠️ PROCESS NOTE (Builder 2026-08-30) — collision EIGHT, and this one is the control experiment for note
  seven: its prescribed fix would have prevented it, and I did not do it.** Note seven, filed hours earlier,
  says in bold: **`git fetch origin main` again immediately before *starting* each new task, not only before
  merging** — because claiming is a publication, not a lock, and the §12 checklist only fetches at start of run.
  This run fetched once at 15:04, shipped the print-size item, then picked up the per-run **night count** off
  the backlog and built it end to end — engine `_capture_hours`, schema 19 `capture_hours_json`,
  `capture_night_count`, the caption clause, 16 tests, all green. The `…-7y6nlj` Builder had merged the
  **identical design** — same column name, same helper name, same read-time bucketing, plus the nameplate,
  gallery and stats surfaces mine deliberately deferred — as **v0.315.0 at 14:30**, i.e. *before this run even
  started*. A three-second fetch at the top of the task would have found it on `main`, fully merged, with no
  ambiguity to reason about.
  **What that costs and what it buys:** roughly an hour of build time thrown away, against a fix that costs one
  second. **The failure was not the claim protocol — it was reading the backlog as the source of truth for what
  is done.** It isn't; `main` is. A backlog entry says what *was* open when someone last wrote to the file, and
  in a two-Builder-per-hour world that is stale by construction. Two habits follow, and they are cheap enough to
  be unconditional: (1) fetch before *each* task, as note seven says; and (2) before writing a line, `git log
  --oneline origin/main -20` and grep it for the item's own nouns — "nights", "capture_hours" would each have
  hit `1b8daaf` immediately. The stand-down itself followed the established pattern (take `main`'s
  implementation wholesale, re-apply only what is genuinely additive; theirs was strictly more complete, so
  nothing was re-applied) — but the cheapest collision is the one you never start.

- **⚠️ PROCESS NOTE (Builder 2026-08-30) — collisions SIX AND SEVEN, in one run, against one other Builder —
  and claiming early did NOT prevent them, because the other run claimed early too.** Branch
  `claude/compassionate-galileo-xkjuvl` claimed the recipe-drift guard and the engine QA-lead sweep in its
  **first** commit and pushed inside a minute, exactly as notes one-to-five prescribe. `…-fj2p70` had claimed
  the *same* drift item (plus the zoom clip) at roughly the same moment, on its own branch, and merged first;
  it then also shipped the "Tonight, live" follow-ons that this run had picked up as its third task. Both runs
  built two of the same three things, well, in parallel. **What that tells us:** the claim protocol is a
  *publication*, not a lock — it only helps an agent that re-reads `main` **between** tasks, and neither did
  (both fetched once at the start, per the checklist). **The cheap fix, and the one this note is really for:
  `git fetch origin main` again immediately before *starting* each new task, not only before merging** — it
  costs a second and would have caught both of these before a line was written. The §12 checklist's per-task
  block should say so; it currently only fetches at start-of-run.
  **How this run resolved it, for the pattern:** it took `main`'s implementation wholesale rather than
  re-litigating naming, then re-applied on top of *their* code, in *their* names, only the parts its own
  version had that theirs didn't (three, listed in that entry). That is much cheaper than a semantic merge and
  leaves one implementation on `main`. **Don't** try to keep both, and **don't** discard your own work
  unexamined — diff the two and port the delta.

- **⚠️ PROCESS NOTE (Builder 2026-08-29) — the FIFTH concurrent-duplicate collision, hours after the fourth:
  two Builders built the Scout's "What's in my picture?" item at the same time. I stood mine down at merge
  time; `77a6122` (v0.293.0) had landed first.** *(Same single root cause as all four notes below — neither
  of us moved the item to **In progress** before starting. It is the top unclaimed beginner feature in this
  section, so it is what any Builder picks the moment the bug queue is dry; with runs every hour, two
  overlapping picks is the expected outcome, not bad luck.)*
  The two implementations were near-identical — same card, same "What's in it?" toggle name, the same reuse
  of `AnnotatedImage` + `croppedAnnotationView` + History's exact annotations cache key, and the same three
  geometry refusals — which is more evidence that a well-written spec entry has one natural implementation.
  **Two things mine had that the shipped one may not, in case a future run wants them.** (1) The read-out
  used the existing `describeFieldObjects`, so each object came with *where it sits* ("toward the top-left")
  rather than only its name; the shipped version's one capped line is the better fit for the "extremely busy"
  page, but the position phrases are the half a beginner uses to actually find the smudge. (2) Its marker
  tests reported `clientWidth`/`clientHeight` the way a browser does, so they assert the pins are really
  *placed* — without that stub jsdom measures the box at 0×0 and `objectMarkerLayout` returns nothing, so a
  test can only assert the words. Worth borrowing the next time anyone touches that card.
  **The cheap fix remains the one nobody does:** claim the item in **In progress** in the *first* commit of
  the run, and push that commit early — a Builder that fetches before starting then sees it.

- **⚠️ PROCESS NOTE (Builder 2026-08-29) — the FOURTH concurrent-duplicate collision, and this time it was a
  whole feature: I built the "Universe map" independently and STOOD DOWN on it at merge time, because
  `4b5131b` ("My map") had landed first. Recorded because the convergence is the useful signal and because
  two things mine had are not in what shipped.** *(Same root cause as the three notes above: neither of us
  claimed the item in **In progress** before starting, which is the one rule in AGENTS §11 that would have
  caught it. The item was the top ⭐ owner-requested feature in this section, so it was the obvious pick for
  any Builder that ran while the bug queue was dry — the collision was close to inevitable.)*
  Both reads landed on the same skeleton: a **third mode on the existing Sky page** (not a new route), the
  per-pixel frame-count sibling thresholded at `coverage_trim.DEFAULT_MIN_FRAC` as the "enough detail" mask,
  a **server-rendered PNG** rather than a client-side WebGL layer, a cache keyed on "has any target's newest
  picture changed", and an explicit exaggeration of small pictures with the caption saying so. When a feature
  is re-derived this closely twice, the shape really is the natural one. Theirs landed first, so I dropped
  mine wholesale rather than merge two all-sky renderers.
  **What differed, in case a future run wants either.** (1) **Exaggeration.** Theirs applies **one shared
  factor** to every picture, so relative sizes stay honest (a six-panel mosaic really does look bigger than a
  single field) — that is better than mine, which floored each picture at a minimum on-canvas size
  independently and so quietly equalised a mosaic and a single frame. (2) **Projection.** Mine was a numpy
  **Hammer** projection rather than matplotlib's `aitoff`; Hammer is *equal-area*, which is what would make
  the "how much of the sky have I seen?" idea below answerable for free. Aitoff is not, so that idea needs
  re-scoping or an equal-area second pass before anyone builds it. (3) **Unplaceable targets.** Mine drew a
  dot for a target with a known RA/Dec but no placeable picture ("you have been here"); worth checking
  whether the shipped map drops those silently, and if so, filing it. Nothing else mine had is worth porting.

### Verified non-issue (Builder 2026-08-12): "another hour would cut its noise" — from "Features"

- **VERIFIED NON-ISSUE (Builder 2026-08-12) — the "say 'another hour would cut its noise about N%' in *one* voice"
  item (filed 2026-08-04, above in Friendliness) is **already consistent** for the two surfaces that actually make
  the marginal-return claim; nothing to build unless a third one appears.** *(Checked, not assumed.)*
  `seestack/nightplan.noise_gain_from_more_time(t)` returns `1 − √(t/(t+1 h))` and its callers print
  `round(gain·100)`; the frontend's `readiness.noiseReductionHint(t)` computes
  `Math.round((1 − √(T/(T+3600)))·100)` — the same formula, the same extra hour, the same rounding, so the Tonight
  card and the Target page's readiness card cannot disagree on the number. The remaining surfaces the entry listed
  (`integrationTrend`, the "cut your noise ~N×" at-completion badge) answer a **different** question — noise
  removed *so far* by stacking N subs, not the marginal return of one more hour — and the entry's own "care" note
  says not to collapse those. Recorded so a future run doesn't re-derive this; if the two ever drift, the fix is a
  frontend mirror of the engine helper, not a re-wording.
  _(**Correction, Builder 2026-08-16:** the formulas do match, but the check stopped at the formula and missed the
  **zero-integration guard**, where the two genuinely disagreed: `noiseReductionHint` returns `null` for
  `exposureSeconds <= 0`, while the planner printed `round(1.0·100)` = *"another hour would cut its noise about
  100%"* on every un-shot target. Found by dogfooding a running build; fixed in **v0.263.2** (see Bugs). The
  lesson worth keeping: "same formula" is not "same sentence" — compare the **guards** too.)_

### Process note (Builder 2026-09-03): a "baseline is green" claim can be a lie — from "Infra"

- **⚠️ PROCESS NOTE (Builder 2026-09-03, found by tripping over it — a run's "baseline is green" can be a
  statement about nothing).** `AGENTS.md` §7 tells every run to confirm the suite green before changing
  anything, and the natural way to do that in a tool call is
  `python -m pytest -q ... 2>&1 | tail -15`. **A pipeline's exit status is the *last* command's**, so that
  reports `tail`'s 0 whatever pytest did. This run's baseline "passed" in about a minute with an output tail of
  `inifile: …` / `rootdir: …` — which is not a summary, it is pytest's **usage-error** block: `--timeout=600`
  was on the command line and **`pytest-timeout` is not installed** in this environment, so pytest exited 4
  without collecting a single test, and the pipeline said 0. Three commits were written on top of an unverified
  tree before the shape of that output was noticed.
  **The rule, and it is one line:** never pipe the suite. `python -m pytest -q > run.log 2>&1;
  echo "EXIT=$?"` — then read the file. (`set -o pipefail` would also do it, but a redirect is what a later
  reader can check.) A summary line that does not end in `passed` / `failed` is not a result.
  **Two follow-ons worth a moment from whoever is next in this area:** (a) add `pytest-timeout` to the `dev`
  extra in `pyproject.toml` — §7's own suggested invocation uses `--timeout`, so the manual currently documents
  a flag the environment rejects, and a genuinely hung test can otherwise burn a whole run; (b) `scripts/
  agent-setup.sh` could print the one-line non-piping invocation as the recommended form, since it already
  prints the suite command and that is where a run copies it from.

### Negative result, measured (Builder 2026-09-03) — from "Infra"

- **⚪ NEGATIVE RESULT — MEASURED, so nobody re-treads it (Builder 2026-09-03, while building the frozen-fit
  channel v0.328.2).** *Does the editor's **STF** stretch disagree between preview and export the way `asinh`
  did before v0.325.0?* The question is a fair one — `tone.stretch` mode `stf` anchors on the image's own
  robust per-channel median and σ, exactly the kind of whole-image statistic the A2 sweep (which looked at
  *pixel-sized parameters*) would not have caught. **The answer is no, and the reason is worth keeping.**
  Measured on a 1600×2400 synthetic OSC frame at proxy steps 2, 3, 4 and 6: preview vs the export's own pixels
  at the same positions differ by **0.0002–0.0004 mean and at most 0.003 max** of a 0–1 tone, and the sky level
  lands within **0.0005** every time. The editor proxy is a **strided decimation** (`rgb[::step, ::step]` in
  `seestack/edit/proxy.py`), which is an unbiased sample of the pixel distribution, so median and MAD survive
  it. The `asinh` bug was a different mechanism: `render_preview_png_full_res` compared an **area-averaged**
  1024 px preview against native, and averaging genuinely does lift the min, lower the 99.5th percentile and
  shrink σ. **The transferable rule: striding preserves a distribution's statistics, averaging does not** — so
  a statistic-anchored op is only at risk where the smaller array was *resampled*, not where it was strided.
  (The same measurement anchored through the new `stats=` channel is 0.00000 at every step, which is the
  control saying the harness could have shown a difference had there been one.)

### Process note (Builder 2026-09-02): a full pytest run's cost — from "Infra"

- **⚠️ PROCESS NOTE (Builder 2026-09-02, measured after it cost the end of a run) — a full `pytest` run leaves
  ~9 GB behind in `/tmp/pytest-of-root`, and three runs fill the container's whole disk allowance.** Measured,
  not guessed: after a baseline run plus two post-sync re-runs, `du -sh /tmp/pytest-of-root` read **28 GB** and
  `df` reported 0 bytes free — at which point pytest itself starts erroring (a wall of `E`s from ~80 % onward,
  as `tmp_path` factories fail with ENOSPC) and the shell can no longer write its own output. It looks exactly
  like a catastrophic regression and is nothing of the kind; the fix is one command:
  **`rm -rf /tmp/pytest-of-root`**, which is safe (pytest keeps only the last few runs' fixture dirs for
  post-mortem) and instantly returns the space. **What to do:** if you expect to run the suite more than twice
  in a run — which any Builder that syncs with `main` and re-verifies will — clear it *between* runs rather
  than after the failure, and treat "errors that begin partway through a suite that was green an hour ago" as
  a disk symptom until `df` says otherwise. Deletes still succeed when writes don't, so recovery is always
  available; a fresh session is never needed for this.

### Pre-existing test-harness quirk (Builder 2026-08-29) — from "Infra"

- **⚪ PRE-EXISTING TEST-HARNESS QUIRK (Builder 2026-08-29, tripped over while spot-checking a merge; recorded
  so nobody spends a run thinking their change broke it) — naming an engine test file and a `tests/webapp/` one
  on the SAME pytest command line can make `tests/webapp/conftest.py` not apply, so every `client` fixture in
  the run errors with "fixture 'client' not found".** *(Severity: none to the product — the **full** suite
  (`python -m pytest -q`) is unaffected and green, and each file passes alone. It only bites an agent running a
  hand-picked subset, which is exactly what an agent does while iterating. Confidence: reproduced.)*
  Repro, entirely on files that predate this note:
  `python -m pytest tests/test_drizzle_reject.py tests/webapp/test_last_night.py tests/test_livesession.py
  tests/webapp/test_target_live_session.py -q` → 8 errors, all "fixture 'client' not found". The same four files
  in pairs, or either directory alone, pass. Swapping in different engine/webapp files reproduces it too, so it
  is about the *interleaving*, not any one file.
  **Working around it costs nothing:** run subsets **per directory** (`pytest tests/webapp/... -q` and
  `pytest tests/... -q` as two commands), and trust the full suite as the gate — which AGENTS.md §5 already says.
  **If someone fixes it:** it smells like conftest/rootdir resolution interacting with `tests/webapp/__init__.py`
  (the package makes `tests.webapp` importable, and pytest's conftest collection for a mixed arg list is
  order-sensitive). Confirm the mechanism before changing anything — the current layout is what every green run
  in this repo's history used, so a "tidy-up" here risks the suite for a convenience fix.

### Harness papercut (Builder 2026-08-27) — from "Infra"

- **⚪ HARNESS PAPERCUT (Builder 2026-08-27, tripped over it and verified it on pristine `main` — recorded so
  the next agent doesn't spend the time I did) — naming `tests/webapp/…` and `tests/…` files in the *same*
  `pytest` command line makes `tests/webapp/conftest.py`'s fixtures vanish: every webapp test errors with
  `fixture 'client' not found`.** *(Not a bug in the app, and **not** a real failure — the plain
  `pytest -q` full run is unaffected, and either directory on its own is fine. Size: S, or close it as
  documentation. Confidence: reproduced on `origin/main` with no local changes:
  `pytest tests/webapp/test_gallery.py tests/test_stack_memory_guard.py tests/webapp/test_video_sharpen_still.py`
  → `39 passed, 22 errors`, all "fixture not found".)*
  **Why it matters at all:** an agent verifying "did I break anything?" naturally reaches for exactly this
  shape — the handful of files around a change, which routinely straddle both directories — and reads 26
  errors as its own regression. That is a wasted diagnosis every time it happens.
  **Two honest options, in order of preference.** (a) *Document it*: one line in AGENTS.md §7 next to the
  existing run recipes — "verify subsets one directory at a time, or just run the whole suite" — which costs
  nothing and is the whole of the fix from an agent's point of view. (b) *Understand and remove it*: it is an
  import-mode / rootdir interaction (`tests/` has no `__init__.py` in the mix, and the suite is imported as
  the `tests` package by `tests/synth.py` consumers), so a `consider_namespace_packages` or `importmode`
  setting in `pyproject.toml` may well close it — **but do not change either setting speculatively**: they
  affect how the *whole* suite is imported, and a green run is the only thing standing between this project
  and a bad merge. Only worth (b) if someone can show the setting change with the full suite green
  before and after.

### Measured negative result (Builder 2026-08-16) — from "Infra"

- **MEASURED NEGATIVE RESULT (Builder 2026-08-16, checked rather than assumed while fixing v0.263.4) — do NOT
  spend a run sweeping the frontend for more `wrap="nowrap"` + `flex: 1` clipping; there is exactly one, and it is
  fixed.** *(Recorded so the obvious follow-on is declined once instead of re-litigated.)* The Gallery button bug
  looked like the tip of a pattern — `wrap="nowrap"` appears **123 times** across `frontend/src` and `flex: 1` in
  ~20 files — so the overflow probe above was run over `/`, `/library`, `/gallery`, `/best`, `/sky-so-far`,
  `/tonight`, `/storage`, `/calibration`, `/jobs`, `/moon-sun` and a populated target page, at **1440 px and
  420 px**, with the sample loaded and stacked. **Zero further overflows.** So the combination is only harmful
  when a `flex: 1` child sits next to a fixed-width sibling in a container narrower than their sum, which is rare;
  the other 122 `nowrap`s are pairing badges or icons that genuinely fit. Re-run the probe after any card-layout
  change rather than grepping for the pattern.

### Verified non-issue (Builder 2026-08-13) — from "Infra"

- **VERIFIED NON-ISSUE (Builder 2026-08-13, checked rather than assumed while shipping the guard above) — the two
  pace *implementations* agree; only the constants were ever the drift risk.** *(Recorded so nobody re-treads it.)*
  `session_recap.recent_night_pace_s` (server) and `clearNights.ts::estimateClearNights` (Target page) were driven
  against each other over **300 randomised night sets** — varying night counts (1–9), subs per night (1–60),
  exposures and per-night rejection rates — built as real projects and read back through `nights_breakdown`, and
  they agreed on **every** case, to within 1e-6. That includes the edges worth naming: fewer than two productive
  nights → no pace on both sides; the all-duds set where the client shows its *"kept almost nothing — worth
  checking focus"* advisory and the server reports no number (both surfaces then say nothing about nights); and the
  `n_frames > 0` pre-filter the client applies, which is a no-op because a night is a group of frames by
  construction. So the *ordering, windowing, productivity filter and median* all match; the constants guard above is
  the only enforcement that was missing. **If a fourth surface ever needs the pace, prefer serving the server's
  number over adding a third implementation.**

### Dev-infra note (Builder 2026-07-29): `npx vitest run` on a high-core box — from "Infra"

- **DEV-INFRA NOTE (Builder 2026-07-29) — a bare `npx vitest run` flakes catastrophically on a high-core
  machine.** On a container that reports many CPUs, vitest spins up one jsdom worker per core and exhausts
  resources: the environment silently fails to initialise (`environment 0ms`) and ~500 tests fail spuriously
  with `ReferenceError: document is not defined` even though each file passes in isolation. It is NOT a product
  bug and NOT a code regression — CI's 2-core `ubuntu-latest` runner doesn't hit it (few workers). **If you see a
  wall of `document is not defined` failures, re-run with bounded parallelism:**
  `npx vitest run --pool=forks --poolOptions.forks.maxForks=2` (all 1336 tests pass, ~200s). Only worth pinning
  in `vite.config.ts` if CI ever actually flakes this way — speculative today, so left as a note, not a change.
  (Recorded so a future agent doesn't lose a run diagnosing phantom failures.)

---

## 2026-09-08 (Builder, branch `claude/sweet-babbage-wvv6ff`) — collision #13: two Builders built the overlap gain in the same hour, and the second threw its copy away

**What happened.** This run took two tasks. The first — the Scout's "While you
were asleep" digest — shipped as v0.388.0. The second was the READY size-L
image-quality entry, cross-panel gain matching from the overlaps. It was
implemented end to end: `seestack/stack/overlapgain.py`, the stacker pre-pass,
a shared-sky fixture in `tests/synth.py`, 11 new tests, measured at **37.2 % →
4.6 %** on a 0.6× hazy panel with the fitted gain ratio 1.669 against a true
1.667. On the pre-merge `git fetch` it turned out that
`claude/sweet-babbage-xm81q4` had merged **the same feature** as v0.387.0
roughly an hour earlier — same module name, same function name, same
measurement to within a rounding.

**What was done about it.** The duplicate was **deleted, not merged and not
"improved on"**. Their implementation is on `main`, green, and carries the one
guard that matters most (`MIN_OVERLAP_CORRELATION`, a Pearson correlation across
the overlap strip — a stronger form of the log-ratio scatter test this run's
copy used, and arrived at the same way: by a fixture inventing a confident gain
out of unrelated stars). Two of this run's choices differ — a 2 % neutral band
so an even mosaic re-stacks bit-for-bit, and picking each panel's *typical* subs
rather than its clearest — but both are unmeasured against theirs, and
re-opening a shipped, tested pass to substitute untested preferences is exactly
the churn §1 warns off. If either is ever wanted, it is a small change on top of
what shipped, with a measurement; nothing was filed, because neither is a known
defect.

**Why the §11 rule did not catch it.** It was followed: `git fetch origin main`
+ `git log --oneline origin/main -30` grepped for the item's nouns, at the start
of the run. The other run's work landed **during** the build — commit
`68f48f8d` at 07:06, this run's task-2 was already underway — so the log was
honest when it was read and stale before a line of the second task was written.
That is the shape of every one of the thirteen: the fetch bounds *how early* a
collision can be detected, not *whether* one happens.

**The one thing that would have helped**, and it costs nothing: for a task the
backlog sizes at **L**, re-fetch and re-grep once more *before writing code*,
after the design read. This run spent ~40 minutes designing against the entry
(reading `photometric.py`, `align_one`, the stacker hook) and never re-checked
in that window — which is precisely when the other run's merge landed. The
existing rule says "before starting each task"; on a long task the useful moment
is later than that. Cheap, and it is the only lever a Builder has that does not
require coordination it cannot do.

---

## 2026-09-08 (Builder, branch `claude/sweet-babbage-xm81q4`) — the fixture that *looked* like a mosaic and let a new pass invent a 2.6× gain

**One task this run** (v0.387.0, cross-panel gain matching in a mosaic's
overlaps). Two things it learned are about *how to check work*, not about the
work, so they live here.

**1. "It is a mosaic" is not the same as "its overlaps hold the same sky", and
only one of those is testable by shape.** The engine's existing mosaic fixture
(`tests/test_photometric_mosaic_auto.py::_hazy_mosaic_project`) draws a fresh
star field per *frame*: two panels stepped 80 % of a field, overlapping on the
canvas, each holding stars the other has never seen. It is a perfectly good
fixture for everything it was built for — per-panel photometric behaviour, panel
bins, provenance — and it says so in its own docstring ("Both panels use the
*same* per-sub star seeds", which makes the two halves *statistically* alike, not
*positionally* alike). What it cannot carry is any claim about the **overlap**.
The new pass was written against it, measured a 2.6× gain between two
equally-exposed panels, and applied a 28 % step — the manufactured panel grid the
pass exists to prevent — and the only reason that surfaced was that an unrelated
existing test (`test_haze_within_a_panel_is_gain_matched_out`) asserted the panels
still matched afterwards. **Without that one assertion, this would have shipped.**
The lesson generalises past this pass: before measuring anything *between* two
regions of a synthetic canvas, check the fixture puts the same photons in both.
`tests/synth.star_catalog` + `make_shared_sky_field` now exist for that (the
test-side twin of what `webapp.sample_data` gained in v0.386.0), and
`tests/test_overlap_panel_gain.py` uses them.

**This is the same shape as the D1 lesson recorded on 2026-09-07** ("six tests had
the bug pinned in a fixture that contradicted its own comment"). Twice in two days
a defect survived because the fixture, not the code, was where the wrong
assumption lived. A fixture is an assertion about the world; it deserves the same
adversarial reading as a function.

**2. The bug the false positive exposed was worth more than the false positive.**
The fix was not "use a better fixture" — that only hides it. Overlapping
*footprints* mean two WCS solutions agree, which a **mis-solved panel** also
achieves while pointing somewhere else entirely. So the pass now correlates the
shared strip before believing it (`MIN_OVERLAP_CORRELATION`), and correlation is
blind to gain — precisely the quantity being measured — so a genuinely hazy panel
still passes while unrelated sky does not. A synthetic fixture stood in for a real
failure mode nobody had thought to guard against.

**3. Two of the run's defects were my own, found by measuring rather than
reading.** The first implementation aligned each sub onto a *coarse* canvas WCS
**and then** block-folded it again — a double downsample that happened to give the
right answer (both panels were squashed identically) while doing something the
docstring did not describe. And the fit's consistency check originally dropped
disagreeing pairs until the residual fell, which always terminates: a loop-free
graph fits *any* ratios with exactly zero residual, so "it agrees now" was
guaranteed rather than earned. Both were caught by writing a test that stated the
intended arithmetic (`test_the_block_fold_lands_a_window_where_the_canvas_put_it`,
`test_ratios_that_never_settle_stand_the_whole_pass_down`) instead of a test that
only checked the end-to-end number, which was green throughout.

**4. The end-to-end check that mattered was the sample nobody wrote for it.**
Stacking v0.386.0's mosaic sample — four panels, one at ×0.85 signal, built by a
different run for a different purpose — recovered panel scales of [0.999, 1.174]
against a true 1/0.85 = 1.176. A fixture written by the same run that writes the
feature can only confirm the author's own model; one written earlier, elsewhere,
for something else, is evidence.

---
## 2026-09-08 (Scout, branch `claude/admiring-brahmagupta-luiss8`) — mosaic Auto/editor + coverage-trim + ASTAP filesystem re-audit CLEAN; one verified friendliness bug found and fixed (the goal chip)

**Baseline.** Fresh `source scripts/agent-setup.sh`; stacking+calibrate subset green
(`-k "stack or accumul or align or mosaic or drizzle or calibrat or reject or weight or coverage"`:
**1776 passed / 2 skipped**). Ran the priority-1 dogfood the right way this time —
`scripts/agent-dogfood.sh --mosaic --editor`, which stacks a real 2×2 mosaic sample and drives the editor
on the **mosaic** run, not the 6-frame field.

**Dogfood verdict — the mosaic Auto/editor path is healthy.** Mosaic detected (`coverage_is_mosaic` True,
four pointing groups); **Auto would trim 7.9 %** of the union canvas (well under the ~15 % D1 threshold); the
Target/edit/stack pages show nothing overflowing and **no console errors**; every one of the 21 editor ops
re-rendered its live preview with no failed request on both the single-field *and* the mosaic run (the mosaic
drive's tail `page.waitForTimeout: … browser has been closed` is the harness's own 900 s teardown, not an app
error — every op that ran before it re-rendered cleanly). This is the first recorded dogfood that drove the
editor on a mosaic; it agrees with the code-level D1/D2 hardening (v0.382.4/.5).

**The one find — fixed this run (v0.386.2).** The "Is it enough yet?" chip printed a mosaic's per-panel-scaled
goal **unrounded**: `goal ~14.526171875 h (3.63-field mosaic)`, while the verdict sentence beside it already
rounded via `readiness.ts::fmtGoal` ("~14.5 h"). `Target.tsx:1451` bypassed `fmtGoal`. Exported `fmtGoal` and
used it for the chip; regression test in `Target.test.tsx`. Frontend-only.

**Adversarial re-audits that came back clean (read the code, not just the tests):**
- `seestack/edit/coverage_trim.py` — `panel_coverage_level` / `well_covered_mask` (the D1 fix): the
  per-panel-vs-peak reference is correct; the fractional-bounds return keeps the trim scale-independent between
  the strided trim map and the preview proxy grid. No bug.
- `webapp/pipeline.py` walk-away thresholds — `_auto_stack_readability_hold` compares total readable vs
  `prior_max` (n_frames_used across runs); total-to-total, conservative on a mosaic (a vanished panel drops
  readable below prior_max → holds). No per-panel/peak confusion. No bug.
- `seestack/solve/astap.py` — filesystem side effects: solves a `shutil.copy2` scratch copy inside a
  `TemporaryDirectory`, never points ASTAP at the source, reads `.wcs`/`.ini` before teardown. Guardrail-safe
  (never touches `incoming/`). No bug.
- Editor preview↔export parity (the A2 family) — every pixel-unit param scales by `ctx.proxy_scale`
  (`background._scaled_box`, `detail`'s scaled `sigma_spatial`/unsharp knee, `stars`' `scaled_px` footprint and
  `starmask.star_mask`'s internal `size_px/scale`, `geometry.crop_bounds`' full-res degenerate test). No bug.
- The recent `render/thumbnail.render_preview_png_full_res` consume-in-place change (v0.386.1) reads correctly;
  its byte-parity test pins it. No bug.

**Minor doc-inaccuracy noted, not filed as a bug (cosmetic):** `seestack/render/thumbnail.py:730` still says
`stack_detail_mask` uses "the same 'at least min_frac of the **peak**' rule" — but `well_covered_mask` now
measures against **one panel** (`panel_coverage_level`), not the peak (the D1 fix). A comment lag, not a code
defect; worth a one-line correction next time thumbnail.py is touched.

## 2026-09-08 (Builder, branch `claude/sweet-babbage-5fx14v`) — collision twelve **and** thirteen, in one run, against one other run — and the timing that made it unavoidable

**What happened.** This run shipped three tasks and **two of them were built
simultaneously by another Builder** (`claude/sweet-babbage-niew4h`), which merged
first as **v0.382.5** (D2) and **v0.383.0** (the Storage "only copy" sentence).
Both of this run's duplicates were **dropped whole** at merge time — branch reset
to `origin/main`, only the unique commit cherry-picked — rather than merged or
re-litigated. That is the standing default (see the 2026-09-08 D1 note directly
below): an item on `main` is done, and a second implementation of a shipped fix
is churn on a live install.

**The two implementations agreed, which is the useful finding.** On D2 both runs
independently landed on the same rule — count only frames whose solve has *run*,
identified by the `solve_failed:` reject reason, because a failure deliberately
leaves `accept` alone — and both corrected the same four existing fixtures that
had pinned the bug by building "unsolved" frames the solver would never leave.
On Storage both wrote a `Project.source_frames_under` with the same signature and
the same "never `stat` under `incoming/`" pin; theirs matches the prefix with
`substr`, this one with an escaped `LIKE`. When two runs converge that precisely,
the backlog entry was doing its job — which is also why both runs picked it.

**Why claiming would not have helped, again.** Both runs started within minutes of
each other and the other run's first push landed at 01:44–01:45 UTC, by which time
this run had already written both fixes. The §11 rule that *would* have caught it
is the cheap one: **`git fetch origin main` before starting each task, not just at
start of run** — the second duplicate (Storage) was begun well after the other
run's D2 commit existed, and a fetch at that moment would have shown D2 on a
branch and prompted a different pick. Recorded because this is the second run in
two days to learn it the same way.

**What did survive** is the item neither run's peer touched: the lucky-imaging
pass-2 demosaic skip (**v0.383.1**). Three "READY" entries were filed by the
2026-09-07 backlog-readiness run and two Builders picked from the same three in
the same hour — with only three ready items, a uniform-random pick among the top
four (§11) collides about a third of the time. **The backlog being thin on
*ready* work is itself the collision risk**, which is a Scout-side finding, not a
Builder-side one.

---

## 2026-09-08 (Builder, branch `claude/sweet-babbage-niew4h`) — the eleventh D1 collision, and the one thing that would have caught it

**What happened.** Two Builder runs picked **D1** within the same hour and both
finished it. The other run (`claude/sweet-babbage-8hitfe`) merged first, as
**v0.382.4**; this run's own D1 — same diagnosis, a different reference statistic
— was **dropped whole at merge time** rather than re-litigated. That is the right
call and worth writing down as the default: an item that is on `main` is *done*,
and replacing a shipped fix with a second implementation of the same fix is churn
on a live install, not an improvement.

**Both fixes were real, and they differ.** Theirs (`panel_coverage_level`) finds
the lowest coverage plateau with a sorted-window scan at a *relative* tolerance —
so it survives weighted (non-integer) coverage, needs no verdict from the caller,
and is monotone-safe by construction: it can only ever lower the threshold and
keep more of the picture. Mine (`panel_coverage_depth` + `coverage_peak_is_overlap`
+ an explicit `is_mosaic` threaded from the stacker into the editor and the sky
map) also kept a **skirt guard**, so a shallow halo of drifted frames is still
trimmed rather than becoming the reference. Theirs stands down on that case on
purpose and says so. Nothing here argues for reopening it; recorded only so a
future run reading both branches knows the difference was deliberate.

**The lesson, and it is not "claim earlier".** §11 already says claiming is a
publication, not a lock, and both runs claimed. What would actually have caught
this is the check §11 *also* prescribes and that neither run ran late enough:
**`git fetch origin main` immediately before the first line of code, and again
before the first line of the *next* task** — not once at start of run. This run
fetched at start (D1 was open), then worked for two hours across three tasks and
only fetched again at merge time, by which point the duplicate was complete. The
cheap habit: fetch, `git log --oneline origin/main -30 | grep <the item's code
nouns>`, *then* write. Ten seconds; it would have redirected this run's first two
hours to the second and third tasks it went on to ship anyway.

**Second, smaller note — the disk.** Three full-suite runs filled the container
(`pytest-of-root` reached 28 GB, and pytest keeps the last three runs' `tmp_path`
trees). The symptom is not "out of disk": it is an `OSError: [Errno 28]` from
pytest's own **cacheprovider** at session teardown, after a green run, which reads
like a test failure. `rm -rf /tmp/pytest-of-root` between full runs, and
`-p no:cacheprovider` if a run must not die at the finish line.

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

**Late in the run a 🔴🔴 landed on `main` and took over, which is the right
order.** The third external audit filed D1 — Auto cropping every mosaic to its
panel overlaps — while this run's own work was in its pre-merge suite. A verified
wrong-result bug on the owner's primary workflow outranks a finished-but-unmerged
improvement, so: merge what is green, then take the bug. Claiming it took one
commit and one push *before* reading the code, because two runs picking a fresh
🔴🔴 in the same hour is exactly the collision the claim board exists for.

**The thing worth carrying forward from D1 is not the fix, it is the fixtures.**
The rule was wrong for mosaics from the first version of the module, and three
audits and twenty clean sweeps missed it. The fix itself is one function. But
**six tests shared a fixture that called a 62 %-of-canvas region a "thin
single-frame fringe"** — and a large region at a lower depth is not a fringe, it
is a shallower panel. Every one of those tests passed *because* it asserted the
bug. So the bug was not merely untested; it was **pinned**. When a fix makes
several existing tests fail at once, read their fixtures before touching either:
the question "is this test protecting behaviour, or encoding the defect?" is
answerable, and here the answer was written in the fixture's own comment
contradicting its own numbers.

**Two smaller notes from the same fix.** A statistic that reads a *distribution*
needs an absolute floor as well as a fractional one — on a map of a few dozen
covered pixels, "8 % of the pixels" rounds down to "one pixel is a plateau", which
is a statement about the sample size and not about the picture; the floor is what
let every small and legacy map keep exactly today's behaviour. And the property
worth *testing* was not the fix but its blast radius: the new reference is always
at or below the peak, so the mask can only grow — the worst case is leaving fringe
in, never trimming a panel away. That one test is what makes the change safe to
merge unattended.

**A harness trap that cost a few minutes.** `git stash` before `git merge
origin/main` on a branch with uncommitted work does exactly what it says and the
merge then reports success over a tree missing your changes; the tell was the
file-changed notices. `git stash pop` after the merge restored it, but the safer
order is to commit first and merge second.

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
