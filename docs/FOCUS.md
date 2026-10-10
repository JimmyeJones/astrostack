# Current focus — AstroStack

*Last edited 2026-10-10 (Builder, next run — **the queue held nothing ungated again, so this run read the
previous run's fix as a lead a sixth time — and the lead was not another piece of arithmetic, it was the
CLIENT. SHIPPED as v0.492.61.**
v0.492.57 made the run-scoped `…/editor/auto-preferences` GET stop claiming a taste the picture has no room
for, and recorded the stand-down for its siblings in one sentence: the feedback POST *"deliberately
measures nothing … the run-scoped read the chips row re-fetches after every tap is what narrows it again,
one request later."* Every clause of that is true **of the server**. But `AutoFeedback.tsx` writes the
POST's answer straight into the run-scoped query cache on success, so the un-narrowed sentence is what the
owner *reads* until the refetch lands — and on the owner's own shape (a deep clean stack, where
`auto_recipe` measures `denoise_strength` exactly 0.0 and "Over-smoothed" is marked) the **first** tap
rendered
```
Auto is running with less smoothing for you, based on your recent feedback.
```
one line under a toast saying the picture had not changed. That is the exact sentence v0.492.57 exists to
delete, re-asserted in direct answer to the tap, four versions into the work.
**The method note, and it is the one to carry forward: a cost stand-down ("this endpoint will not measure
that") bounds the server's answer, not the screen's.** Wherever one endpoint in a family can answer a
question and a sibling cannot, the *merge* of the two answers is a place the honest answer can be
overwritten by the cheap one — and that merge lives in whichever layer holds the cache, which is not the
layer the stand-down was written in. Ask where the cheap answer is **rendered**, not only where it is sent.
**The precedent was already in the same function, one field over:** that `setQueryData` had a four-line
comment refusing to take the POST's `inert_cues` literally for the identical reason, written two versions
earlier. `note` had simply *joined* `inert_cues` in being a claim about a picture — v0.492.57 is what moved
it into that class, and nothing re-read the merge afterwards. So **when a fix gives an existing field a new
dependency, re-read every place that field is copied.** The two are now one exported pure function,
`mergeMeasuredPreferences(data, old, scoped)`, shared by the feedback and reset mutations, so a third
picture-dependent field cannot be added without meeting the rule.
**Server untouched and the stand-down respected:** the POST still measures no picture, its response is
byte-for-byte what it was, `describe_profile` is still the only author of the wording, and the Python test
that pins the POST's plain claim is unchanged. The kept note is safe because it can only *under*-claim
(it has not heard about the step just taken); the one carve-out is the tap that walks the last bias back to
neutral, where the server's own `neutral` flag is the free signal that there is no taste left to describe.
**Nothing removed:** the note is also where **Reset** lives, so both cases were pinned separately — with a
taste already stored the narrowed note and its Reset stay on screen unbroken through the tap; only the
first tap from a neutral profile waits for the refetch, and there was no note (and no Reset) there a moment
earlier either. Tests **+9 vitest** (4 pure, 5 jsdom), **fail-before 4 of them** by reverting the one line.
The inbox was checked first — **four open, all previously acted-on and owner-gated** — and there were **no
open PRs**. Earlier notes stand below.)
*Last edited 2026-10-10 (Builder, next run — **the queue held nothing ungated, so this run read the previous
run's fix as a lead and found the SAME untruth one line down the screen. SHIPPED as v0.492.57.**
v0.492.54 marks the Auto feedback chips the picture has no room for; v0.492.56 made the tap on a marked
chip say so. **The "why Auto shifted" note directly underneath that row was still saying
*"Auto is running with less smoothing for you, based on your recent feedback."*** — on the owner's own
shape, where `auto_recipe` measures `denoise_strength` **exactly 0.0** and emits a byte-identical op list
with that taste and without it. So after three versions of work the editor marked a chip as dead, answered
its tap honestly, and then claimed the taste was in force one line below. Reproduced both directions
against `origin/main` (the mirror is a very noisy stack with the denoise pinned at `_AUTO_DENOISE_MAX`) and
**both fail-before through the real run-scoped `…/editor/auto-preferences` GET**.
**The method note, and it is the one to carry forward: the chips row and the note are two different
questions about the same arithmetic.** `inert_auto_cues` asks *"would one more step reach the recipe?"*;
the note asserts *"Auto is running X for you"*, about the taste in force **now**. Neither implies the
other, and the test says so: three "too dark" taps leave the *cue* at `MAX_STEPS` (chip marked) while the
taste they built is in full force (note rightly claims it). **When a fix makes one surface honest, ask what
else on that screen makes the same claim from different arithmetic.**
`presets.inert_bias_params` is the sibling predicate in the sibling shape — emitted op params with and
without each stored bias, through the helpers `auto_recipe` is built from, so it cannot drift and so it
catches `min(…, _AUTO_DENOISE_MAX)`, which runs *after* the taste and is in no `_PARAM_RANGE`. **Free:**
at most six dict builds on the single `measured_auto_knobs` pass that GET already pays for. **Nothing
removed** — every phrase survives, the stalled ones in a clause, because the taste is library-wide *and*
because that note is the only place the editor's **Reset** link lives, so a note that went `None` would
take a control with it. Frontend untouched: the note is a server-authored string and `describe_profile`
stays its only author.
**And the collateral was built in the same run: v0.492.58.** v0.492.57 is a bug the Auto dogfood pass
could not have found, and the reason is the same shape as last run's — it read the chips, their marks and
the **toast**, and nothing read the note. The toast is gone in 4 s; the note is what the owner sees every
time they reopen the picture, and it is where **Reset** is rendered. `dogfood_editor.mjs` now prints it
before any tap and after each one, and flags an absent note as a finding.
**On its first run the new reading caught the instrument twice more — v0.492.59 and v0.492.60 — and the
pattern is the run's real lesson: four times over, this family failed by REPORTING rather than by
crashing.** (1) A note claiming a taste it did not have. (2) A probe reading the transient toast and not
the persistent line. (3) A selector that swept up a one-click *suggestion* ("Hold back highlights (0.05)",
offered on the 2x2 mosaic), tapped it as a chip, filed three false findings and then timed the whole mosaic
drive out. (4) And v0.492.59's own fix degrading silently, because `agent-dogfood.sh` runs the drive from a
**copy** so its relative path to the cue table found nothing and an empty label list meant "skip the
filter" — the validation run read exactly like a fix that had never been written. So the chip labels now
come from `autoFeedbackCues.cases.json` (already the chips/`_CUE_STEP` contract) via `ASTROSTACK_REPO`,
anything else in the alert is named and left alone, **failing to read the table is itself a finding**, and
each tap is fenced. The upside: the pass can now report a **missing** chip, which is the one symptom here
a screenshot can never show — the v0.492.52 bug, whose own record says a dogfood could not have found it.
**Validated on a third pass: both page sweeps clean, both editor drives clean across all 21 ops and both
Auto passes, mosaic trim 8 %, ZERO findings** (four, all false, two passes earlier). Three method notes in
[`PROCESS-NOTES.md`](PROCESS-NOTES.md), the general one being: **a finder may not fall back silently, and
the blast radius of one bad step should be one step.** The inbox was checked first — **four open, all previously acted-on and
owner-gated** — and there were **no open PRs**. Earlier notes stand below.)
*Last edited 2026-10-10 (Builder, same run, tasks 2 and 3 — **the run's best finding came from building the
instrument that could see the surface it had just changed. SHIPPED as v0.492.55 and v0.492.56.** Five runs
in a row had written "a dogfood could not have found this" about an Adaptive-Auto fix and treated it as a
property of the bug. It was a property of the **probe**: the chips row lives *inside* the "What
Auto-process did" alert, so it does not exist until the button is pressed, and nothing in this repo's
tooling had ever pressed it — `dogfood_editor.mjs` drove the pipeline, `dogfood_probe.mjs` photographs the
editor as it opens. **v0.492.55** adds an Auto pass to the editor drive: it clicks Auto-process, prints the
alert as one paragraph, lists which chips the app marks as unable to move this picture against which are
live, **taps one of each and prints what the app says back**, then presses Reset.
On its first working run it did both jobs. It **confirmed v0.492.54 on the owner's shape** (full-size
mosaic: 10 chips live, `Over-smoothed` and `Core looks flat` marked — exactly what the arithmetic predicts
for a stack with no denoise and no highlight protection, and nothing more), and it **found a PRIORITY-1
bug**: the marked chip still answered *"Thanks — Auto will lean that way for you"*, the exact sentence
v0.492.53 exists to stop, one mechanism over. `_feedback_limit_note` only covers the tap whose dead end is
in the **store**; a chip dead because the **picture** is at its limit moves the bias, so the server sends
no `limit_note` and the row fell through to the thanks. **SHIPPED as v0.492.56**, free: the chip is already
wearing the right sentence, so the mutation reads the mark the tapped chip carried and uses it — the POST
still measures nothing, the server stays the only author of the wording, and Auto's no-op rebuild is now
skipped (~0.6 s saved rather than spent).
**Three method notes, all in [`PROCESS-NOTES.md`](PROCESS-NOTES.md).** (1) **When "a probe could not have
found this" appears twice in a row, ask what the tooling cannot reach, not what the bug was hiding
behind.** (2) A finder that waits for the page to go quiet **cannot read what the page says transiently** —
`<Notifications />` auto-closes in 4 s and `settle()` waits 7 s plus idle. (3) `.at(-1)` on a locator's
texts is **not** "the latest thing on screen": the page carries several `mantine-Notifications-root`
containers and all but one are empty, so the last match is `""` however long you wait. Both probe bugs
looked identical from outside — a confident *"the app said nothing"* — which is the dangerous failure mode
for an instrument: it does not crash, it reports.
The run's first task and its notes stand below.)
*Last edited 2026-10-10 (Builder — **the queue held two leads and the right one was the one whose own
write-up had already made the decision. SHIPPED as v0.492.54.** v0.492.53's lead reproduced and priced the
second way an Auto feedback chip can be dead — the bias moves, `_nudge`'s range clamp swallows it — and
named two cheaper homes for the answer, picking **(a)**: report it from the request that already measures
the picture, so the chips row can **mark a dead chip before it is tapped** rather than apologise
afterwards. That is what shipped, on the **run-scoped `…/editor/auto-preferences` GET** rather than on
`…/editor/auto` (the Recipe response is a `Recipe`; the run-scoped read is the one the chips row already
consumes, with the same `autoCrop` query key, and it was already classifying the run). **The numbers, on a
1000×1500 proxy:** the twelve questions cost **0.145 ms** once the knobs are in hand; the one new
measurement is **284 ms** beside the **313 ms** that GET already paid to classify; the predicate the lead
cut is **1 233 ms per live tap**. The feedback POST's cost and response are byte-for-byte unchanged, and
`AutoFeedback.tsx` re-fetches the read after a tap (a third "Too dark" can be the chip-killer) keeping the
marks it has while that is in flight.
**Four method notes.** (1) **Extract rather than mirror, and then prove it.** The lead's one prohibition
was "do not mirror the clamp arithmetic in a second place — that drift caused three of the last five
editor bugs", so `auto_recipe`'s measured-knob block *and* its tone/detail op assembly now go through
`measured_auto_knobs` / `auto_knob_values` / `auto_op_params`, and the extraction was checked over **910
recipe builds against `origin/main` — 0 differences** before anything was built on it. (2) **Pin the
report against the thing it reports on, not against its own helper.**
`test_inert_cues_agree_with_the_recipe_itself` asks `auto_recipe` directly, before and after each of the
twelve taps, on four pictures from four stored tastes — a cue is reported inert *exactly* when the op list
is byte-identical. (3) **A faithful end-to-end predicate finds the mechanism the analysis missed.** The
lead listed the store cap and `_PARAM_RANGE`; comparing *emitted op params* also caught
`min(…, _AUTO_DENOISE_MAX)`, which runs **after** the taste, so any measured denoise ≥ 0.9 kills
"Over-smoothed" for all three of its steps. (4) **Two best-effort answers from one `try` is one answer too
few** — the archetype decides which bucket the taste is read from (losing it is the v0.492.50 symptom)
while the knobs only feed a hint, so they fail separately, with a test for it.
**UI rule honoured:** nothing removed, nothing disabled. A dead chip is faded, has a tooltip, and the row
gains one line of legend — because an inert tap is still a real library-wide preference, which is exactly
what the sentence says.
**"Bugs (fix these first)" now holds the *(ii)* half of that lead only — whether an inert chip should be
given room rather than a label — plus the older gated LEADs and ⚪ notes; do not re-litigate the numbered
stand-downs.** The inbox was checked first: **four open, all previously acted-on and owner-gated**, and
there were **no open PRs**. Earlier notes stand below.)
*Last edited 2026-10-09 (Builder, fifth run of the day — **the inbox was clear, there were no open PRs, and the
bug came from asking the table NEXT TO the one that paid out last time. SHIPPED as v0.492.53.** v0.492.52 read
`_CUE_STEP` as a population (*which parameters are reachable both ways?*); `_PARAM_RANGE`, immediately below it,
takes a different question — *which chips can actually move this picture?* **Not all of them, on every realistic
picture**, and `AutoFeedback.tsx` answered every tap with *"Thanks — Auto will lean that way for you"* over a
byte-identical re-render. Two mechanisms, and **only the free one shipped**: the stored taste having nowhere to
go (a bias at `MAX_STEPS`, so the *fourth* identical tap on any of the twelve chips; and
`_PARAM_MIN_STEP["highlights"] = 0`, so **"Core looks flat" is dead from the FIRST tap** on any picture Auto is
not already holding back). Equal effective biases either side of the tap ⇒ every input to `auto_recipe` is
equal ⇒ the recipe is byte-identical, so it needs no proxy and no measurement.
**The other mechanism is REPRODUCED, MEASURED and FILED as a LEAD, not built** — and the reason is the useful
part. The bias moves while `_nudge`'s range clamp swallows it: on a clean deep stack (`noise_fraction` 0.000,
the owner's own shape) `auto_recipe` leaves `denoise_strength` at exactly 0.0 and **"Over-smoothed" moved
nothing on 5 of 5 taps**; on a noisy one, **"Too noisy"** and **"Over-sharpened"** were inert the same way and
"Over-smoothed" needed **3 taps to undo one**. The exact predicate — rebuild `auto_recipe` either side of the
tap — **was written, then cut on a measurement**: 639 ms per build on a 1000×1500 proxy, i.e. **1.28 s added to
every live tap** on the PRIORITY-1 hot path to label a minority. The LEAD names the two cheaper homes, and the
better one is better UX too: report it from `…/editor/auto` (which already pays that cost on every Auto click)
so the chips row can **mark a dead chip before it is tapped** rather than apologise afterwards. **Read the
LEAD before touching `_PARAM_RANGE`** — widening it changes what Auto emits for an existing saturated profile.
**Three method notes** in [`PROCESS-NOTES.md`](PROCESS-NOTES.md): (1) *a comment that asserts a relationship
between two tables is a claim you can check* — `auto_prefs` says its ranges are "a touch wider than
`auto_recipe`'s own measurement clamps", and that is true of **one** of the six; (2) *build the exact check,
then price it, and be willing to cut it* — and **an existing test that pins a call count is a performance
guard nobody labelled as one**: the five `classify_target` shape-spy transcripts went red while the slow path
was in and are untouched in what shipped; (3) `Recipe.to_dict()` **cannot be compared** (fresh `uid` per op,
fresh `updated_utc`), and it fails in the direction that hides nothing — the first repro printed "MOVED" for
all 60 taps and read as a clean bill of health.
A **`--mosaic --editor` dogfood was CLEAN** (both passes, both editor drives, all 21 ops, trim 7.9 %, zero 500s)
— **but it took two runs, and the first one's finding was mine**: `npx vite build` emptied `webapp/static/`
under the dogfood's own uvicorn and the probe reported a `/live` 500 on a page this diff never touched. **New
trap, now in [`AGENT-ENVIRONMENT.md`](AGENT-ENVIRONMENT.md): serialise dogfood → `vite build`/`vitest` →
`pytest`, and read `$DOGFOOD/server.log` before writing down a lone 500.**
**"Bugs (fix these first)" holds one new entry — the LEAD above, marked reproduced/measured — plus the older
gated LEADs and ⚪ notes; do not re-litigate the numbered stand-downs.** The issue inbox was checked first
again: **four open, all previously acted-on and owner-gated**, both of the day's observer comments opening
"not a new report". Earlier 2026-10-09 notes stand below.)
*Last edited 2026-10-09 (Builder, fourth run of the day — **the inbox was clear, the one actionable lead was
claimed by an open PR, and the bug this run shipped came from reading a TABLE AS A POPULATION rather than as a
list. SHIPPED as v0.492.52.** Adaptive Auto's `_CUE_STEP` maps eleven plain-language chips to one Auto
parameter and a signed step. Read down it, it is eleven fine lines; asked of the whole table — *which
parameters are reachable in both directions?* — five had a pair and **`green` had one line**. So three taps on
"Too green" take Auto's SCNR amount **0.7 → 1.0** (full green-cast removal) and **nothing in the vocabulary
brings it back**: only `DELETE /api/editor/auto-preferences`, which discards *every* taste the owner has
taught Auto, or `DECAY_DAYS` at **one step per 90 days**. Reproduced against `origin/main` by offering all
eleven cues to a saturated profile — every one left the bias at `+3`. Fixed with one cue
(`"too_magenta": ("green", -1)`) and one chip beside "Too green" in the existing Colour group, symmetric at ±3
(Auto *sets* green removal at 0.7, so less of it is a real taste, unlike `highlights` which starts at its
floor), plus the guard that outlives it: a shared `autoFeedbackCues.cases.json` pinning
`AUTO_FEEDBACK_CHIPS` ↔ `_CUE_STEP` from both sides, and a test that **every parameter a cue reaches is
reachable both ways**.
A **`--mosaic --editor` dogfood ran after the change and was CLEAN** — *"nothing overflowing, no console errors"* at desktop and phone widths on both targets (zero overflow / clipped-label / squeeze findings), both editor drives clean across all 21 ops — **and, for the second run in a row, it could not have found this run's bug**: the symptom was a *missing* chip, and a probe that photographs what is on screen cannot report what is absent. Record in [`PROCESS-NOTES.md`](PROCESS-NOTES.md).
**Three method notes worth carrying forward.** (1) **Read a table as a population.** A list of entries that
are *supposed* to be symmetric is a property you can state, and a property you can state is a test — so ship
the invariant, not just the missing row. (2) **Dead output vocabulary is evidence about the input
vocabulary** — the inverse of v0.492.50's "a bucket nothing reads". `_BIAS_PHRASE[("green", False)]` held a
complete sentence (*"with a lighter green-cast removal"*) that `describe_profile` could never say, and
`auto_recipe`'s own comment described a state no cue could reach. Grep for a phrase/label/branch keyed on a
value nothing produces. (3) **A mid-run merge can change a call's arity** — PR #1101 landed mid-run on both
frontend files this touched and added a third argument to `sendAutoFeedback`; re-run the touched test file
after syncing rather than trusting the pre-merge green.
**"Bugs (fix these first)" still holds no verified, ungated open bug.** The issue inbox was checked first
again (**four open, all previously acted-on and owner-gated — nothing new owed**), and "Features that serve
real workflows" holds **no ready entry**: every open bullet there is shipped, closed-as-already-built,
measured-and-stood-down or deprioritised, and the two live ones are gated ("constellation lines *only if* a
dataset is already bundled"; "unpack a big archive as a job", gated on someone uploading one). **Five editor
dead ends are written out in [`PROCESS-NOTES.md`](PROCESS-NOTES.md) so they are not re-walked** — the
`proxy_scale` divergence between the two Auto builders (they agree), the five preview-fidelity advisories (all
five rendered), `star_mask`'s footprint at its two call sites (scaled inside `starmask`), the `OP_PHRASES`
mirror (pinned), and the border trim's over-crop bound (closed, four levers measured and rejected). **One
baseline note:** the full suite at `-n 8` dropped one test on a `_wait_job` **60 s timeout under load**
(`test_an_ordinary_seestar_drop_says_nothing_about_its_skips`), which passes alone in 8.1 s and is green in
`main`'s CI — a harness trap not yet in `AGENT-ENVIRONMENT.md`; re-run the single test before calling `main`
red. Earlier 2026-10-09 notes stand below.)
*Last edited 2026-10-09 (Builder, same run, second task — **the residual the first task filed is SHIPPED as
v0.492.51, and the entry's own prescription is why it was one task rather than two.** The editor's *per-run*
border-trim switch reached `…/editor/auto`, so **Auto honoured it** and with the trim off classified the whole
canvas — while neither classification surface could see it (`api.presetSuggestion` posted no body at all; the
feedback body is a cue; the run-scoped GET has none). So with the switch flipped, v0.492.50's divergence
re-opened through the one input Auto takes and the classification did not. **The method note: when a fix makes
two sites agree, the agreement is only as good as the narrowest input they share** — v0.492.50 made them agree
about the *setting* and left them disagreeing about the *override*, which is the same bug one level down. The
override now travels on all three requests, `None` still means the setting (so the default answer is
byte-for-byte v0.492.50's), and both frontend query keys carry the flag because flipping the switch changes
which question is asked rather than staling the answer. **"Bugs (fix these first)" now holds NO lead from this
run at all** — only the older gated LEADs and the ⚪ notes; do not re-litigate the numbered stand-downs. The
run's earlier notes stand below.)
*Last edited 2026-10-09 (Builder, third run of the day — **the method that found v0.492.49 found another PRIORITY-1
editor bug immediately: read the fix you just shipped as a lead.** v0.492.49 narrowed the *fourth*
`classify_target` caller and wrote in its own docstring that `auto_recipe` "keys its taste profile on this very
function's verdict". It does — and a **fifth** caller, forty lines further down the same file, is the place that
*writes* that profile. **SHIPPED as v0.492.50.** `editor._classify_run` — behind the editor's *"How did Auto do?
Tap what you'd change:"* chips and the run-scoped "why Auto shifted" note — classified the **whole canvas**, so on
a ragged mosaic the owner's tap was filed under `cluster` while Auto keyed the same profile on the kept rectangle,
which is confidently *nothing*. `auto_prefs.effective_biases` reads `by_type[object_type]` and nowhere else, so the
tap saturated in a bucket nothing read: **three "too dark" taps moved Auto's stretch target 0.1967 → 0.1967**
against the 0.2567 they are worth, under a toast that says *"Thanks — Auto will lean that way for you"*. Measured
first: the two archetypes differ on **8 of 30** ragged four-panel canvases, the cheapest at a **13.6 % trim**.
**Two method notes worth carrying forward.** (1) **A fix that names its sibling has named a population, not a
sibling** — "these two must agree" is worth grepping for *every* caller of the thing they agree about, in the same
run, because the copy-paste that made the fourth wrong made the fifth wrong too (the four mirrored lines are now
one function, `classify_run_measured`, so a sixth caller cannot be wrong the same way). (2) **A write side and a
read side of one store are not two surfaces that merely disagree** — a mislabelled bucket is cosmetic, a bucket
nothing reads is a feature that silently does nothing, so grade the two differently when you find them.
**"Bugs (fix these first)" still holds no verified, ungated open bug** — the two leads this run and the last one
filed, the older gated LEADs and the ⚪ notes. A **`--mosaic --editor` dogfood ran while CI chewed on the PR and
was CLEAN** (third consecutive clean pass on that pair; the five mosaic Target-page sentences all point the same
way, trim 7.9 %, both editor drives clean across all 21 ops) — **and it could not have found this run's bug**, the
symptom being a *lack* of change in a recipe. Record, and the probe shape that would catch this family, in
[`PROCESS-NOTES.md`](PROCESS-NOTES.md). The issue inbox was checked first (the method note below): four open,
all previously acted-on and owner-gated, and both of today's Observer comments say "not a new report" in their first
line. Earlier 2026-10-09 notes stand below.)
*Last edited 2026-10-09 (Builder, second run of the day — **the queue was dry, so this run went looking and
found a PRIORITY-1 editor bug by *reading the last run's own collateral note*: SHIPPED as v0.492.49.** The
2026-10-01 record in [`PROCESS-NOTES.md`](PROCESS-NOTES.md) ends "a fourth measurement added later must go
through `measured_region` too" — and there already **was** a fourth, in `webapp/routers/editor.py`, which is why
no grep of `seestack/edit/` ever reached it. The editor's "try this preset?" chip classified the ragged mosaic
border Auto's own last op deletes, so one picture had two archetypes and the canvas's was the worse one (fringe
grain lifts `classify_target`'s threshold → `ext_frac` falls → the verdict walks toward *cluster*). **Measured
before building: the verdict flips on 21 of 210 ragged canvases, the cheapest at a 9.8 % trim** — inside the
band AGENTS.md calls healthy. **The method worth carrying forward: when a run's write-up says "and a future one
must also do X", check whether something already needed X and was missed — a "next time" note is also a
*last* time note.** One lead filed and deliberately not built (the same cue corruption survives with
`auto_crop` **off**, where narrowing would change what Auto emits for an existing setting). **"Bugs (fix these
first)" still holds no verified, ungated open bug** — only that new lead, the older gated LEADs and the ⚪
notes. The earlier 2026-10-09 notes stand below.)
*Last edited 2026-10-09 (Builder — **"Bugs (fix these first)" once again holds NO verified, ungated open bug.**
The Scout's "My map" two-count bug (item 0b) is **SHIPPED as v0.492.48** and its entry is cut to
[`SHIPPED.md`](SHIPPED.md); observer **#1095** shipped as **v0.492.47** earlier in the same run and is closed.
What is left below is the gated LEADs and ⚪ notes — **do not re-litigate the numbered stand-downs.** The "My
map" fix is worth one line of method for the next run: **the entry's three candidates were all count-vs-count
reconciliations, and the fix was to notice that only one of the two sentences needed to carry a count at all.**
The map's subtitle counts what it draws (checkable by looking at it); the read-out beside it is about *area*, so
it now says only that, and the singular-subject special case that existed purely to agree with a count went with
it. When two surfaces disagree about a number, ask whether both of them actually need to state it. A run that
finds this page dry should call `list_issues` first — **that is what found #1095 this morning** — then dogfood
and file what it finds. The two earlier 2026-10-09 notes stand below.)
*Last edited 2026-10-09 (Builder — **observer issue
[#1095](https://github.com/JimmyeJones/astrostack/issues/1095) arrived on the morning of this run, untriaged, and
it was the run: it is SHIPPED as v0.492.47 and CLOSED.** It outranked the backlog's front (item 0b, low/latent
and not firing on his library) because it **is** firing on his: `field_fulls_of_sky` counted a canvas's *bounding
box* as sky covered, so **a single pointing read as up to 2.29 field-fulls** and **46 of his 50 single-field
pictures crossed the planner's 1.3 mosaic line** — which nulls `framing`, `mosaic` and `size_arcmin`, so **six
big objects lost a framing verdict the catalog has**, five of them the "shoot it in mosaic mode" advice the
planner exists to give (M 42 at 85' is 119 subs at one
pointing, 43.8 % of its canvas empty, read as 2.22 fields). Fixed by subtracting the share the run itself recorded
as uncovered (`stack_runs.uncovered_frac`, a column of the row `target_field_fulls` already read — no extra query,
no file read), plus the rounding that would otherwise have hidden it (`fieldsOfSkyLabel` said "about 2 fields of
sky" for 1.25; it now says "a little over one field of sky" below 1.5, and `nightplan._fields_of_sky_phrase`
mirrors it). **Method notes for the next run:** (1) **`list_issues` first, again** — this is the third run in a
row where the real front of the queue was an untriaged issue rather than the backlog, and this one was 2 hours
old; (2) **a measurement fix beats a threshold flip** — the 1.3 line is the engine's own `AUTO_UNION_AREA_RATIO`
and was left alone, which is why M 42 lands at 1.25 on the near side of a line nobody moved; and (3) **when a
number's error has been priced as "the forgiving direction", check the price** — `perPixel.ts` had the mechanism
written down ("the canvas counts its uncovered corners, so the figure errs shallow — it warns a little early")
and the margin it assumed was small was up to 2.29× on his own data. **THE FRONT OF THE QUEUE IS AGAIN ITEM 0b**,
the Scout's "My map" two-count bug — still the one verified, ungated open bug, still low/latent, S to write and
**M to decide the source of truth**. The two 2026-10-09 notes below stand.)
*Last edited 2026-10-09 (Builder — **observer issue
[#1090](https://github.com/JimmyeJones/astrostack/issues/1090) is now CLOSED in both of its halves.**
**The front of the queue is the Scout's item 0b** — its "My map" two-count bug, filed in PR #1093, which merged
while v0.492.46 was in CI and is now the one verified, ungated open bug (low/latent, S to write). Everything
else is the gated LEADs and ⚪ notes.
Its mid-copy half shipped as **v0.492.46**: nothing between the scan's walk and the stack re-asked how many
files the drop folder holds, so a folder caught mid-copy read as a complete, settled target through *every*
guard (they all count frames already ingested) — which is how `C_9` was published and auto-edited from **6 of
its 742 subs**. New `_auto_stack_arrival_hold` asks that question as a **fresh** directory read and subtracts
the two library-wide tallies the incoming-lag note already computes, so it is the *distinct* `source_path`
count (#878's double registration would otherwise hold every shared folder for ever) minus what no scan can
ever read (#880's ~147 rows cost not even one poll). **Un-strandable by two independent bounds** — that
evidence, and `AUTO_STACK_ARRIVAL_META_KEY` recording the folders' on-disk *shape*, so one shape buys one hold
— because an unbounded count comparison switching auto-stack off for a target is worse than the bug. **Method
notes for the next run:** (1) *the UI rule decided the shape of the fix's output* — the arrival hold reports
through the **existing** `auto_stack_held_settling` key and "Subs still arriving" alert rather than a second
always-on banner, since the two guards catch one situation from opposite ends and a beginner needs the same
sentence either way; (2) v0.492.45's own note paid off immediately — **re-reading every string the newly-live
guard can print** caught the alert claiming only the settle window's harm ("would re-stack the whole target
over and over"), which is not this case's harm at all; and (3) **a test that must pass in both directions is
still worth writing** — the one-poll bound and the known-unreadable subtraction are green against `main` by
design, because they are the guard-rails against stranding rather than the bug. The 2026-10-09 note on the
clock half stands below.)
*Last edited 2026-10-09 (Scout — **rotation sweep (4) the webapp routers filed one verified bug, and the queue
front did not change.** The front stays #1090's mid-copy half (item 0, the Builder's, medium-high). What I filed
is a **second verified, ungated open bug — but low/latent** (item 0b): the "My map" page's baked map subtitle
("N of your pictures") and the sky-coverage read-out beside it ("Your N pictures cover …") count "pictures" by
**different rules** (`_my_map_pictures` keeps a WCS-less run via a nominal-field fallback; `sky_area_union_deg2`
drops it), so they disagree by the number of displayed pictures that have a preview but no usable WCS —
**reproduced** 2 vs 1 on a two-target library, **not firing on the owner's current library** (observer #1015
measured 83/83 displayed runs placeable), filed-not-fixed because the fix is a wording / source-of-truth choice.
Issue inbox: **all five open issues already acted-on, nothing new owed** — the only fresh activity is a
2026-10-08 Observer follow-up on #878 that is explicitly "not a new report" and *strengthens* the shipped stance
(the duplication did not recur across an overnight 3,700-frame ingest). `--mosaic` dogfood **CLEAN** and coherent;
the bundled runs carry synthetic WCS so the two Sky counts agree there, which is why the filed bug is latent.
**Rotation: (4) done — next is (1).** Record in `docs/PROCESS-NOTES.md`. The 2026-10-09 Builder note stands below.)
(Builder — **`list_issues` had FIVE open, not the four this page said**: observer
[#1090](https://github.com/JimmyeJones/astrostack/issues/1090) was filed on the morning of 2026-10-08 and was
still untriaged. It was this run, and it is the front of the queue. **Its clock half is SHIPPED as v0.492.45**
and its **second, independent half is now the one verified, ungated open bug** at the top of "Bugs (fix these
first)" — see item 0. What shipped: `_auto_stack_settle_hold`, the guard that exists to stop the hands-off chain
publishing "a picture of a night that is not over", had **never held anything and structurally could not** — it
asked `Project.newest_accepted_sub_time()`, which preferred `frames.source_mtime` on the strength of a docstring
claiming it was "stamped at ingest". It is the *source file's own* mtime, so every timestamp-preserving copy
records the **capture** time and the 20-minute window was spent before the first sub of a folder reached the DB
(the observer measured it on **118 of 118** drop folders). Reproduced here end to end before the fix — subs
ingested *that second* read as **504.0 h** old — and after it reads 0.0 h and holds. New `frames.ingested_at`
stamped centrally in `Project.add_frame`; the answer is the **later** of arrival and capture, so the hold can
only have become more cautious. Ungated `ALTER`, no `SCHEMA_VERSION` bump, every existing row NULL → an upgrade
is unchanged until the next sub arrives. **What is still open is the mid-copy half**, which the observer was
careful to say the clock would *not* have fixed, and which is what actually published a picture from **6 of 742
subs**. **Method notes for the next run, in `docs/PROCESS-NOTES.md`: call `list_issues` before believing a dry
backlog; read an observer issue's "explicitly not claimed" section, because a good one means two tasks; and when
a fix turns a dormant guard on for the first time, re-read every string it will now print** (this one said
"waiting on N still being shot" for a folder that is merely still copying). `docs/SHIPPED.md` **is no longer the standing
housekeeping task — it is done**: the two 2026-09-05 bulk-move sections went whole and in order to
`docs/archive/SHIPPED-2026-09-05-bulk-moves.md`, **62,092 → 35,051 lines**, nothing deleted, verified by
`comm` that no line is missing. ⚠️ **So grep `docs/` rather than `docs/SHIPPED.md`** — anything older than
v0.353.0 is in the archive now, and AGENTS.md §1's grep rule was updated to say so. The 2026-10-08 note stands below.)
(Builder — **#1088 is SHIPPED as v0.492.44 and the issue is closed**, so
**"Bugs (fix these first)" once again held NO verified open bug at that point** — only the gated LEADs and ⚪ notes. The — **#1088 is SHIPPED as v0.492.44 and the issue is closed**, so
**"Bugs (fix these first)" once again holds NO verified open bug — only the gated LEADs and ⚪ notes.** The
"subs waiting in incoming/" note no longer offers a scan it cannot fulfil: the exclusion now comes from what the
scan *recorded* as skipped (`SkippedCalibrationFolder.folder` → `webapp/calibrationskips.py`), **unioned** with
the old `discover` walk so an install that has not scanned since upgrading is unchanged, and matching stays
**exact**. Both of #1088's granularity mismatches were reproduced before the fix and both fail-before through the
endpoint at `assert 6 == 0`. **The prefix roll-up the entry warned about is now a test that passes before *and*
after** (`test_a_light_folder_holding_nested_darks_still_reports_its_lag`) — darks filed inside a *light* unit
must not take that unit's real lag down with them. The three docstrings that asserted "the two sets are
identical" (v0.455.0) are corrected rather than left standing. **Next run: do not re-litigate the gated
stand-downs below; grep `SHIPPED.md` before building.** One thing worth a task of its own, filed in
`docs/PROCESS-NOTES.md` rather than as a bug: `docs/SHIPPED.md` is at 61,998 lines against the 64,000 ceiling the
docs-budget job enforces — **archive** the oldest entries to `docs/archive/`, never delete. The Scout's own
2026-10-08 note stands below.) (Scout 2026-10-08 — **a new observer issue, [#1088](https://github.com/JimmyeJones/astrostack/issues/1088),
verified and filed into "Bugs (fix these first)"** (issue left open with a verification comment; work not done). The
"subs waiting in incoming/" note (`webapp/incominglag.py::incoming_lag`) offers a **Scan incoming** button for a
calibration folder the scan will never import, whenever declared darks sit one directory deep (`Darks/20s/`): the
exclusion compares the plan's *recursive* unit folder (`Darks`) against discovery's *non-recursive* directory
(`Darks/20s`) by **exact** equality, and the two only coincide when calibration frames sit directly in a top-level
folder — exactly the shape the Calibration page's `MAX_DEPTH = 2` nesting invites. **Reproduced end-to-end** through
the real `plan_incoming_units` + `find_calibration_folders` + `incoming_lag`; severity **low/latent** (not firing on
the owner's library today — zero nested directories under his `incoming/`). The naive prefix roll-up is **wrong** —
it misses the `MIN_FRAMES`-floor variant and over-silences darks nested in a light unit — so the robust fix (consult
what the scan *actually* skipped) is Builder-sized; full entry in the backlog. **Rotation sweep (3) ASTAP/ffmpeg
filesystem side effects re-swept CLEAN**: ASTAP still copies each frame into a `TemporaryDirectory` before `-f` (no
`-update`, sidecars read from the temp copy), `video/ffmpeg.py` reads with `-i` and pipes raw frames to stdout (`-`,
never an output path), and the stub-binary readonly-guard tests (`tests/webapp/test_incoming_readonly_guard.py`) are
green in the baseline. **Dogfood** `--mosaic --incoming-lag --calibration` otherwise coherent (incoming-lag note,
mosaic readiness, stack-health all read sensibly); one minor finding — the self-hiding "Repair them" button's label
clips 3 px on phone width — filed under the Bugs "Minor / low-priority" bucket (cosmetic, fix when touching the file).
The other four open issues (#1015, #903, #880, #878) stay owner-gated — #1015's app half shipped, only the owner's
token-mint and the Observer's own clone-pin remain. Baseline 7468 passed / 4 skipped, CI green. Record in
`docs/PROCESS-NOTES.md`. The 2026-10-05 Builder note stands below.) (Builder 2026-10-05 — **closed observer issue #1069 in all four of its halves**: the backfill
guard **v0.492.39**, the destructive delete it was hiding **v0.492.40** (deleting an old stack could delete a
*current* picture), the display fork **v0.492.41**, settled with a signature that reads no files, and **v0.492.42** — the *write* side of the same sentence, found by grepping `SHIPPED.md` for what the earlier runs filed onto the entry they then cut — plus **v0.492.43**, observer #1079's drift guard, found by reading the issue list rather than trusting this page's count. The Scout's
earlier 2026-10-05 edit stands below: all five open issues triaged, rotation sweep **(4) the webapp routers**
CLEAN, `--mosaic` dogfood CLEAN and coherent (trim 7.9 %). Records in `docs/PROCESS-NOTES.md`.) **"Bugs (fix these
first)" now holds NO verified open bug — only the gated LEADs and ⚪ notes.** The earlier Builder 2026-10-05 note stands: a `--mosaic --editor --big` dogfood
after v0.492.38 is CLEAN and the scale-pair rig reads **0 of 16 canvas-independent answers moved**. **The Scout
rewrites this page** when the front of the queue changes; it stays short and dated. If this page and the backlog
disagree, the backlog's "Bugs (fix these first)" wins and this page is stale — fix it.*

## Front of the queue

0. **⭐ THE QUEUE IS DRY: "Bugs (fix these first)" holds no verified, ungated open bug.** 🟡 **The Scout's
   "My map" two-count bug (the prior item 0b) shipped as v0.492.48** (Builder 2026-10-09) and its entry is cut
   to [`SHIPPED.md`](SHIPPED.md) — the read-out beside the map no longer claims a count of "your pictures" at
   all, so the only count on the screen is the map's own, and neither counting rule was changed. A run that
   finds this page dry should call `list_issues` first, then do a dogfood pass and file what it finds. 🟠 **Observer
   [#1095](https://github.com/JimmyeJones/astrostack/issues/1095) — a canvas's bounding box counted as sky
   covered, so 46 of 50 single fields read as mosaics and six big objects lost their framing advice — was
   triaged and SHIPPED as v0.492.47 in the same run it was filed** (Builder 2026-10-09) and the issue is
   closed; it never entered the backlog, so there is nothing to cut. It was taken ahead of 0b because it fires
   on the owner's library and 0b does not. 🔴 **The mid-copy
   half of [#1090](https://github.com/JimmyeJones/astrostack/issues/1090) shipped as v0.492.46** (Builder
   2026-10-09) and the issue is **closed in both halves**; the entry is cut to [`SHIPPED.md`](SHIPPED.md).
   Everything below 0b is gated LEADs and ⚪ notes — **do not re-litigate the numbered stand-downs**; a run that
   finds the backlog dry should call `list_issues` first (v0.492.45's note), then do a dogfood pass and file
   what it finds. **As #1090's remaining half was filed, now shipped:**
   🔴 **The prior front of the queue: the mid-copy half of [#1090](https://github.com/JimmyeJones/astrostack/issues/1090)**
   (Builder 2026-10-09, filed with the v0.492.45 fix of its other half). **A walk-away stack is published from
   the subs a folder had when the scan *walked* it, and nothing between the walk and the stack re-asks how many
   the folder now holds** — so a drop folder caught mid-copy reads as a complete, settled target. It has fired:
   the owner's `C_9` was published **and auto-edited from 6 of its 742 subs**, never QC-graded (`auto_grade`'s
   `MIN_FRAMES_FOR_GRADING` is 10), then re-stacked from 609 seventy minutes later. **v0.492.45 does not cover
   it and the observer measured why** — the folder's copy finished 35.9 min before the stack started, because
   the job spent 39 min stacking the other target first, so the settle window had honestly expired. Size **M**;
   severity medium-high. The full entry carries the fix shape *and* its trap: an unbounded count comparison
   **strands** a target on a file that cannot be ingested at all (~147 such rows, #880), so the hold must be
   bounded to **once per observed on-disk count**. Issue left **open** with a comment naming both halves.
   **Below item 0b it is gated LEADs and ⚪ notes, as before — do not re-litigate the numbered stand-downs.**

0b. **The second verified, ungated open bug — low/latent (Scout 2026-10-09, rotation sweep (4) the webapp
   routers): the "My map" page reports two different counts of "your pictures" side by side.** The map PNG's
   baked subtitle counts a WCS-less picture (nominal-field fallback in `webapp/routers/sky.py::_my_map_pictures`)
   that the `/api/sky/coverage` read-out beside it drops (`sky_area_union_deg2`'s `n_pictures` excludes a master
   with no usable WCS). **Reproduced** 2 vs 1 on a two-target library (one WCS-ful, one WCS-less). Size S to
   write, **M to decide the source of truth** (count only placeable pictures in the subtitle, reword, or drop
   WCS-less pictures from the map). **Not firing on the owner's current library** — observer #1015 measured 83/83
   displayed runs placeable, so it needs an "older/edited" WCS-less displayed run — hence low/latent, below item 0.
   Full entry in "Bugs (fix these first)"; filed-not-fixed.

0a. **The prior front of the queue, now history: "Bugs (fix these first)" held NO verified, ungated open bug.** 🟡 **#1088 shipped as v0.492.44**
   (Builder 2026-10-08) and the issue is closed; the entry is cut to [`SHIPPED.md`](SHIPPED.md). The method note
   worth carrying forward: **a false invariant written into three docstrings is a bug with three heads** —
   v0.455.0's "the two sets are identical, a folder could not fall between them" was in `plan_incoming_units`,
   `_calibration_units` *and* `_calibration_folders`, plus a test pinning the agreement on the one tree where it
   really holds; repairing the comparison and leaving the prose would have handed the next run the same wrong
   model. And **the candidate you reject earns a test when it is the cheap one**: the prefix roll-up is now
   `test_a_light_folder_holding_nested_darks_still_reports_its_lag`, green before and after, so the next run to
   reach for it goes red. The Scout's filing text follows.
   🟡 **As filed (Scout 2026-10-08), now shipped.**
   🟡 **The incoming-lag note offers a scan it can never fulfil when calibration frames sit one directory deep.**
   `webapp/incominglag.py::incoming_lag` excludes a calibration folder by **exact** equality (`if unit.folder in
   skip`), but the plan names the *recursive* unit (`Darks`) and discovery names the *non-recursive* directory
   (`Darks/20s`), so they only match when the frames sit directly in a top-level folder — and the Calibration
   page's `MAX_DEPTH = 2` deliberately accepts the nested shape. Reproduced end-to-end; severity low/latent (not
   on the owner's data today). The prefix roll-up is wrong on two counts (the `MIN_FRAMES`-floor variant, and
   over-silencing darks nested in a light unit), so the robust fix — have the note consult the scan's actual
   `SkippedCalibrationFolder` set — is **Builder-sized**. Full entry (repro, three layouts, fix shape) in the
   backlog; issue left open with a verification comment. **Below this, #1069 is closed in all FOUR of its halves
   (Builder 2026-10-05); the rest is gated LEADs and ⚪ notes.**
   🟠 **The fourth half shipped as v0.492.42** (Builder 2026-10-05), and finding it is a **method note, not a
   sweep**: the previous run filed two consequences "onto #1069's open display half", that half shipped, and the
   entry was cut to `SHIPPED.md` — so nothing in the backlog held them. **A run that ships an entry must check
   what was filed *onto* it**, because cutting the entry deletes the only pointer; grepping `SHIPPED.md` for the
   last runs' own *"deliberately not built"* paragraphs is what a dry backlog should do before a dogfood pass.
   One of the two was mis-severitied as cosmetic and is not: **"Adjust → Save as preview" on a displaced row
   re-rendered the *live* run's preview PNG** (its History thumbnail, Target hero, Library tile and Sky Map
   tile). Measured through the endpoint — the shared preview 64×64 → **86×86 turned 155°**, the rotation stamped
   on the *clicked* row, the live row's `preview_north_up_deg` left **NULL**, which is the exact mismatch that
   column exists to prevent. Refused with 409 (`preview_owner_by_run_id`); the live run — the *writer* — still
   saves, and the Adjust panel keeps every control. The other consequence (a displaced row reclaims no space) is
   answered by v0.492.41's badge. **The class, for the next run: v0.492.40 guarded *deletes* against "a row does
   not own what it points at"; this is the same sentence applied to *writes*. Grep `run.preview_path` /
   `run.fits_path` / `run_artifact_paths` for *writers*, not readers — as of this run the preview save was the
   last one.**
   🟡 **The display fork shipped as v0.492.41** and the whole entry is cut to [`SHIPPED.md`](SHIPPED.md). It took a
   **third** option the entry had not named: two rows naming one `fits_path` *is* the bug (the guard exists to stop
   exactly that), so it needs **no file read** — the listing already holds every row — which keeps the cheap History
   endpoints' no-file-read promise and settles the fork with no migration and no schema change. Its limitation is
   measured: a merge erases the signature (`_carry_pictures` copies under a `_free_basename`), under-reporting rather
   than mis-stating — which is why v0.492.39's sibling guard, already holding the file open, keys on `NAXIS` instead.
   **Next run: the one ungated verified bug is #1088 at the top of "Bugs"** (Scout 2026-10-08, Builder-sized —
   see item 0). Below it is gated LEADs and ⚪ notes; do not manufacture busywork, and do not re-litigate the
   gated stand-downs below.
   🔴 **The serious one on this population shipped as v0.492.40** (Builder 2026-10-05), found by reading while
   scoping the display half: **deleting an old stack could delete a *current* picture.** `delete_run_artifacts`
   unlinks a run's three path columns plus every basename-derived sibling and checked nothing about whether another
   row still names them, so deleting one of the 56 displaced rows unlinked the live run's whole set — **16 files**
   in the reproduction — and **"Prune old stacks" targets the oldest rows first, which is exactly what all 56 are.**
   `purge_stack_run` now asks the DB what other rows still name; the set is re-read per run so the last row of a
   shared group still frees everything, and deleting the *live* row keeps what its displaced sibling serves. Raws
   were never at risk (`incoming/` is read-only). **The next Builder on half (1) has three candidate signatures,
   not two** — the entry's marker-migration and render-time-header-read, plus a zero-file-read one (two rows naming
   one path, which the observer's 71-rows-on-15-paths count corroborates exactly) whose **measured limitation is
   that a merge erases it** (`_free_basename` + per-run copy splits the pair). Details in
   `docs/PROCESS-NOTES.md`.
   🟡 **#1069's ready half shipped as v0.492.39** (Builder 2026-10-05): all three file-reading heals in
   `coverage_backfill.py` now decline a file whose `NAXIS` is not the row's `canvas_w`/`canvas_h` (`_canvas_of`),
   checked before a pixel is read and only on positive evidence. **No wrong number existed on the owner's library** — the observer
   measured every file-derived column NULL on all 56 rows, and an earlier draft of this page said otherwise; both
   fail-befores are synthetic. What the guard is for: `backfill_coverage_shares` is a *third* file-reading heal with
   **no `is_mosaic` gate at all**, so those rows were **one "How's my stack?" away** from a stamped wrong number
   rather than one `is_mosaic` backfill away (it stamps a 0.0667 thin share off the replacement picture); and
   `backfill_seam_residual` *re-measures* a superseded-scale figure, so a mosaic-flagged displaced row has a stored
   0.42 **overwritten** with 2.0542 off a different picture — the `is_mosaic` gate still holds on the owner's 56, so
   that one is a severity finding about the function, not a live condition. The guard adds no new silence (a row that records no canvas heals as before; a
   superseded figure whose master is gone is kept, not cleared), and the invariant it rests on — a real
   `run_stack`'s row canvas *is* its master's `NAXIS`, drizzle included, which `StackEstimate.canvas_w`'s
   "pre-drizzle" docstring makes look doubtful — is pinned by its own test rather than argued. **What is still
   open is the design fork of half (1)**: how the History card *says* a pre-v0.81.8 picture is gone (a one-off
   additive marker migration, or a render-time `canvas`-vs-`NAXIS` check that costs the header read the cheap
   History endpoints promise to avoid). Ten fixtures that let a row's canvas differ from the map beside it were
   made faithful, not loosened.
   🟡 **#1069 as filed (Scout 2026-10-05), severity low.** A closed set of 56 pre-v0.81.7 History rows
   serve a *newer* run's picture and frame count — `Project.repoint_stack_runs` runs only at re-stack time and
   nothing migrated the rows written before the v0.81.7–0.81.8 overwrite guard (mechanism reproduced in the
   code; the per-target counts are the observer's live-library measurement). The pictures were overwritten, so
   the fix is to **say so**, not mend the path — a **design fork** (one-off additive migration marking the rows,
   vs. a render-time `canvas`-vs-`NAXIS` check that costs a header read the cheap History endpoints promise to
   avoid). The **ready-to-build half** is independent and obviously safe: `coverage_backfill.py`'s two
   file-reading backfills lack a `canvas`-vs-`NAXIS` guard and are one filled-in `is_mosaic` NULL away from
   stamping a wrong *number* onto a displaced row. Not #903, not a recurrence of the v0.81.7 bug. Full entry in
   the backlog.
   🟠 **The `sky_sigma` stride bug shipped as v0.492.38** (Builder 2026-10-05): `analyze_proxy`'s σ was a
   function of the proxy's *stride* and nothing else, so the same sky got a sharpen-dominated Auto as a single
   field and a near-saturated denoise as a mosaic — ×1.57 high off a strided grid, `noisy` False→True,
   crossfade weight 0.243→0.789 on *the same pixels*, and in the **over**-denoising direction because the
   recipe is applied to the full-resolution export. Of the entry's three candidates it took **(c)**, in the
   shape that needs no calibration: as a **ratio**. `noise.grain_lag_ratio` = `σ(lag 1)/σ(lag step)` on one
   array in one normalization — the proxy's lag-1 differences *are* the master's lag-`step` differences, so
   the normalization divides out exactly and nothing is calibrated between the grids; `proxy.source_grain_ratio`
   supplies it from un-strided windows of the master (memoized in the proxy sidecar). **No bar was moved**, and
   it is 1.0 by construction on an undecimated proxy and on white noise — so a single-field stack's Auto is
   byte-for-byte what it was. **(b) was rejected on a reason the entry had not spotted** (Auto measures
   `_measured_region`, not the canvas the stacker measured), and the entry's own objection to (b) — an "edited
   proxy mid-session" — does not exist: both call sites pass the raw `get_proxy` array.
   🟠 **The seam finding shipped as v0.492.37** (Builder 2026-10-04): `measure_seam_residual` was not scale-free
   — the bundled mosaic at three sensors read 0.4520 → 0.7075 → 0.8685 on 457 / 907 / 1693 px of the *same* sky,
   so the biggest canvas lost the "the panels of this mosaic evened out" note. The bodies agreed on all three to
   within half an ADU; what moved was how many 0.2–0.9 %-of-the-canvas slivers cleared the absolute
   `min_pixels_per_level` and were then allowed to set the whole `max − min`. The range is now **trimmed by share
   of the canvas**, not by pixel count: a level covering ≥ 1 % always votes at full value, and `share = 0` *is*
   the old range, so the bump of `SEAM_ESTIMATOR_GENERATION` (2 → 3) stays one-sided by construction. The
   per-level *floor* the entry warned about was built first and is measured wrong — it blinds the deep-dither
   catch — and the two bars are untouched. After: 0.0616 / 0.0931 / 0.0000.
   🟡 **#1063 shipped as v0.492.35** (Builder 2026-10-04): the incoming-lag note went silent on the owner's
   double-registered folders because `imported_by_folder` *summed* a folder's tally across targets, so #878's
   duplicates pushed it past the files on disk and `waiting <= 0` dropped the folder — 30 of 54 drop folders
   dark, a 41,727-sub dead zone. The rollup decision the entry left open was settled by **running candidate
   (a)**: `max` across targets fixes the repro *and* cries wolf on two targets holding disjoint halves of one
   folder, so the count is now distinct `source_path`s, taken **only for a folder more than one target
   claims** (a library with no duplication reads not one extra row). What is left below is **gated LEADs and
   ⚪ notes** (owner data, an unmeasured cost, or a numbered stand-down — see `docs/PROCESS-NOTES.md`; the
   2026-10-04 ⚪ is `classify_target`'s `confidence` pinned to 1.0, filed-not-fixed because nothing reads it).
   **Do not blind-flip a gated threshold or re-litigate a numbered stand-down.** Grep `docs/SHIPPED.md`
   before building.

1. **The editor (PRIORITY 1) — "re-audits come back clean" held until 2026-10-04, when one did not.** Judge
   Auto/editor on a tiled mosaic at the owner's scale (`--mosaic --editor --big`); a "What Auto did" trim
   above ~15 % of the canvas is a bug. **v0.492.33**: the preset chip called all three bundled star-only
   samples a *galaxy* at proxy step 1 and a star cluster at step 2, `classify_target`'s opening footprint
   being a fixed 7×7 in **proxy** pixels while `starmask.star_mask` next door had always scaled its own.
   **Reuse the instrument that found it** — the two bundled mosaic samples "differ in scale alone", so asking
   both the same question and diffing the answers tests any claim that should not depend on canvas size
   (lead filed under Infra).

2. **Owner-approved, buildable now: empty** — everything shipped and cut to [`SHIPPED.md`](SHIPPED.md).
3. **Open observer issues — FIVE open, FOUR of them owner-gated (Builder 2026-10-09).** #1090 is the fifth,
   and it was open and untriaged while this page said four: filed 2026-10-08T07:21Z, verified and reproduced
   2026-10-09, **clock half shipped as v0.492.45**, **mid-copy half filed into "Bugs"** (item 0), issue left
   open with a comment naming both. The other four (#878, #880, #903, #1015) carry **no repo code work** and
   stay owner-gated. ⚠️ A MATCHING COUNT IS NOT A MATCHING SET, and a *correct* count goes stale within hours:
   call `list_issues` before believing a dry backlog. The 2026-10-08 text follows.
   **The prior text — FOUR open (Builder 2026-10-08, after closing #1088 in the run that fixed it).**
   **#1088 is CLOSED** — verified, reproduced, fixed as **v0.492.44** and closed with a comment naming the
   version, all in one run (AGENTS.md: an issue whose work is done gets closed in the same run). The four
   that remain (#878, #880, #903, #1015) carry **no repo code work** and stay owner-gated. ⚠️ A MATCHING
   COUNT IS NOT A MATCHING SET: don't trust any count here over `list_issues`. The Scout's 2026-10-08 text
   for #1088 follows. **#1088
   appeared 2026-10-07 and was triaged by the Scout run before this one**: verified against the code, reproduced end-to-end, and
   filed into "Bugs (fix these first)" (item 0 above), severity low/latent, issue left open with a verification
   comment (work not done — the robust fix is Builder-sized). ⚠️ A MATCHING COUNT IS NOT A MATCHING SET: don't
   trust any count here over `list_issues`. The other **four** (#878, #880, #903, #1015) carry **no repo code
   work** and stay owner-gated — #1015's app half shipped (version now on `/api/health`, v0.479.3/.488.2) and only
   the owner's token-mint and the Observer's own clone-pin remain (both outside this repo). The Scout's 2026-10-05
   text for those four stands below.
   **The prior text: FIVE open, ALL now triaged (Scout 2026-10-05).** **#1069 is the one that got
   triaged this run**: verified against the code and filed into "Bugs (fix these first)" (item 0 above),
   severity low, issue left open with a verification comment (work not done). The other four were triaged
   2026-10-04 and **none carries code work** — all are blocked on an owner click/reading, with no new activity
   since needing action: #878 (reconcile shipped v0.482.1/.2 — closes on a reading that shows the 11 pairs
   gone), #880 (both live halves shipped v0.483.1/.2; only the ⚪ exception-repr remainder open), #903
   (prevention still open; existing damage has the v0.479.3 repair), #1015 (repo half shipped v0.488.2; the
   clone-pin + token-mint remainder is out of this repo). Don't trust any count here over `list_issues`.

## Standing frontier (unchanged until a finding says otherwise)

- **Mosaic-scale and walk-away behaviour is the open frontier**, not the single-field engine core.
- **Rotation state.** (1) preview↔export parity on a mosaic canvas — **swept CLEAN 2026-10-02, re-swept CLEAN
  2026-10-06 (Scout)**: the one-click Auto recipe renders proxy↔export within |Δ|≤0.0004/channel at proxy step 4,
  all divergence entering at `tone.stretch`'s documented resolution dependence; the 2026-10-06 re-sweep confirmed
  it from both ends — a code-level A2 audit (every pixel-unit op param scales by `ctx.scaled_px`/`proxy_scale`,
  with documented floors/advisories where the sub-pixel shrink degenerates) and the live scale-pair rig reading
  **0 of 16** canvas-independent answers moved on `--mosaic --big`. **Don't re-run (1).**
  (2) mosaic/walk-away divergence — a threshold taken from a whole-target or *peak* number that is really
  per-panel — swept 2026-10-03 (Scout, yielding the Tonight-planner bug **shipped v0.492.32**) and **re-swept
  CLEAN 2026-10-07 (Scout)**: the whole per-panel threshold family audited engine→webapp→frontend and run on the
  owner's mosaic shape — the best-tonight score/ranking/noise-% are provably scale-invariant (F cancels in
  `1 − √(T/(T+h))`), the stackhealth yardstick's `crop_depth` is the median not the peak, and readiness/thin-stack/
  grain/next-best-move/auto-stack-hold all divide by the per-panel `field_fulls`; the `--mosaic` dogfood read the
  per-panel sentences correctly on the 2×2 (and the single field unscaled). **Don't re-run (2).**
  (3) ASTAP/ffmpeg filesystem side effects — **re-swept CLEAN 2026-10-04 and again 2026-10-08 (Scout)**: ASTAP
  still copies each frame into a `TemporaryDirectory` before `-f` (no `-update`, sidecars read from the temp
  copy), `video/ffmpeg.py` only reads (`-i` in, raw frames out over stdout `-`, never an output path), both files
  substantively unchanged since the last sweep, and the stub-binary readonly-guard tests
  (`tests/webapp/test_incoming_readonly_guard.py`) are green in the baseline. (4) the webapp routers were swept
  2026-10-01, re-swept 2026-10-05 and **again 2026-10-09 (Scout)** — this last one yielded the low/latent
  "My map" two-count bug (item 0b above), the aggregation routers (`plan.py`, `sky.py`, `lifelist.py`,
  `wishlist.py`, `gallery.py`) otherwise clean. Details in `docs/PROCESS-NOTES.md`; don't re-run (1), (2), (3) or
  (4) before a finding says to — **next in rotation is (1).** **The fifth question — does a measurement change when only
  the canvas does? — is now half swept (Builder 2026-10-04): the pure-Python half came back CLEAN** (identical
  Auto op lists and identical verdicts at full resolution and `[::2, ::2]`, every difference at the rounding
  digit), **and the rig was deliberately not landed as a test because its synthetic fixture cannot reproduce
  the pre-v0.492.33 defect** — a green tick with no sensitivity. **The `--big` sample-pair half is now SHIPPED as
  v0.492.36** (`scripts/dogfood_scale_pair.py`, step 4a-ter of the dogfood pass) **and it found two things on
  its first run, both filed under "Bugs"**: `seam_residual` moves 0.6998 → 1.2218 on the same sky through a
  bigger sensor and loses the "panels evened out" note, and `sky_sigma`'s move turned out to be the proxy
  *stride* rather than the canvas. **The seam one is now SHIPPED as v0.492.37** (item 0 above):
  the entry's reproduction recipe held (0.4520 → 0.7075 → 0.8685 here, 10/35/100 s), the share *floor* it warned
  about was indeed measured wrong, and what works is the same bar applied as a **trim of the range** rather than a
  per-level veto — a group of thin levels that together clears 1 % of the canvas still sets the extreme, which is
  what keeps the deep-dither catch alive. Neither bar was flipped. **`sky_sigma` is now SHIPPED too, as v0.492.38** (item 0 above): the
  ×1.57 step-1→step-3 factor is a property of the reprojection's correlation (identical at σ 0.002/0.02/0.2, and
  1.00 for white noise), and the fix is that same correlation **measured** rather than calibrated —
  `σ(lag 1)/σ(lag step)` off un-strided windows of the master, which is dimensionless, so no bar moved and the
  two already-correct cases (undecimated proxy, uncorrelated grain) are 1.0 by construction. So question 5 is
  **answered where it could be asked, and both of its consequences are drained** — and the pair rig that found
  them now reads 0 of 16 moved.
  Next user of the rig: the pair differs in canvas extent *and* proxy stride at once, so ask any `MOVED` line
  of one master at two strides before calling it a canvas bug.
  Caveat for whoever takes it: the raw cues move ~30 % relative while the verdicts hold, so any future
  tightening of a `classify_target` threshold must be checked at two canvas sizes. Details in
  `docs/PROCESS-NOTES.md` and the Infra lead.
- **The single-field core is re-opened only narrowly** (a pixel-unit threshold tested on an eighth-size
  fixture; swept across `stack`/`calibrate`/`edit`/`render`/`qc` 2026-09-28 — CLEAN). Do **not** re-sweep
  `seestack/stack` or `seestack/calibrate` until a new bug is found there (AGENTS.md).
- **The UI rule:** nothing removed, consolidate rather than add, measure before slicing. Tallest pages and
  baselines: `docs/PROCESS-NOTES.md`, "DOGFOOD BASELINE".
- **A beginner feature on a regular cadence**, but the section is empty and the obvious ones are shipped
  (annotation overlay, share caption, print sizes, framing/mosaic advice, moon notes, "bring my pictures up
  to date") — **do not manufacture a marginal one (§4)**; grep `SHIPPED.md` before proposing another.

## How the owner gets builds now

He deploys with `sudo bash scripts/deploy.sh` from the **`stable`** branch (advanced by `.github/workflows/stable.yml`
to the newest `main` commit ≥ 3 days old with green CI) or from a release tag. So a fix reaches him days after it
merges — ship the follow-up to your own change *before* that soak ends.
