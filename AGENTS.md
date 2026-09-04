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

**📋 OWNER FACTS — the authoritative list. If a fact about the owner is not in this
block, it is UNKNOWN: ask via the backlog, never hard-code a guess.** *(Added
2026-09-02 after an audit found `webapp/pipeline.py` hard-coding "ZWO Seestar S50"
onto every baked caption and citing "AGENTS.md §1" as its authority — a fact this
file had never contained. The owner has an S30.)*
- **Scope: ZWO Seestar S30** (150 mm focal length, 2.1° field — confirmed by the
  owner 2026-07-24). **Not an S50** (250 mm, 1.27°). Where the model matters, derive
  it from the frame's own `FOCALLEN`/`XPIXSZ` (`seestack/io/fits_loader.py`) rather
  than assuming either.
- **Install:** TrueNAS/Docker, upgraded **in place**, non-technical owner.
- **Data:** thousands of subs per target (~5,477 on the largest). **Raws live only in
  `incoming/`, with no backup** — see §10, which is not negotiable.
- **Live settings:** `copy_to_cache` **off** (so the app reads the owner's raws in
  place — anything that touches a frame path touches `incoming/`), `auto_stack` and
  `auto_edit_on_autostack` **off**, unless the owner says otherwise.
- **Shooting style:** heavy mosaic user (`<T>_mosaic_sub/`), many targets spanning
  many nights. **Test mosaic-shaped and large-canvas cases, not just a 1080p single
  field** — several 2026-09-02 findings existed only at mosaic scale.

**Priorities, in strict order (the owner set these).** When choosing what to do,
higher on this list wins — always:

1. **Make the editor excellent.** ⚠️ **RE-OPENED 2026-09-02 — do not believe any
   "the editor is well-hardened" claim further down this file.** An external audit
   verified by reproduction that (a) Auto's contrast curve **brightened the sky by
   ~36% on every Auto picture** (`_sky_mode` read the STF's zero-clip spike as the
   sky), and (b) several editor ops **disagreed between preview and export** because
   their pixel-unit parameters were not scaled by the proxy factor — worst on the
   mosaic-size canvases the owner actually has. **✅ BOTH ARE NOW FIXED — A1 in
   v0.326.1, every named A2 instance by v0.327.2 — so don't go looking for them**;
   the priority itself stands, and so does the warning above (a "well-hardened"
   claim is a claim about *known* bugs, and two audits have now disproved one).
   The non-destructive editor is where a good stack
   becomes a good *picture*, and its recurring problems are a live preview that
   doesn't match/behave, clunky and confusing controls, and a weak default
   result. **Go deep here: hunt and fix its bugs, make the controls obvious, and
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

**✅ THE 2026-08-17 CRITICAL WALK-AWAY DEGRADATION BUG IS FIXED (v0.270.1, 2026-08-26) — don't go looking
for it.** The owner's "my images turned out worse" report (787→575→271 frames / noise 0.015→0.015→0.020
across one growing night) was root-caused to `_auto_stack_frame_count` deciding whether to fire purely from
a DB-level accepted+solved count, never checking whether those frames' *files* were readable right now — so
a transient storage problem (storage-side on the owner's box, NOT a code bug; `incoming/` deletion is
already guarded, see §10) let the stack fire, silently drop what it couldn't read, and publish the thinner
result as the target's newest picture; and the attempt marker then stamped the same readability-blind count,
so it never retried. **Both halves shipped:** a readability preflight that holds the target back — without
stamping the marker — when stacking now would land below the minimum-frames floor or *thinner than the best
stack that target already has*, plus a missing-file count stamped beside the attempt marker so a crippled
attempt retries once the files return. Gated on there being unreadable files at all, so a healthy install is
bit-for-bit unaffected. Full write-up in `docs/IMPROVEMENTS.md` → "Bugs (fix these first)"; search it for
**"walk-away"** rather than reading from the top — that section is now ~1,800 lines and the entry is not first.
**✅ EVERY FOLLOW-ON THIS PARAGRAPH USED TO POINT AT HAS SINCE SHIPPED TOO — don't go looking for them
(refreshed 2026-09-03, after a run found this list still sending work at done items).** *Healing* an install
already sitting on a degraded picture from before the fix is `pipeline._auto_stack_degraded_recheck`, which
re-stacks once the data is all readable again rather than waiting for the next clear night. The latent
mosaic **auto-grade population** bug (a star-poor panel graded target-wide and rejected wholesale as "cloud")
shipped as **v0.270.2**, per-panel; and **`photometric_normalize` on the walk-away mosaic path** shipped as
**v0.271.0**, auto-enabled for every mosaic canvas the way `final_gradient_removal` already was. So this
whole family is closed: pick new work from the live sections of `docs/IMPROVEMENTS.md`, not from here.

**🎨 STANDING OWNER PRIORITY (2026-08-08) — the UI is "extremely busy"; fix the information
architecture, page by page.** The owner's top complaint about the live build: *"there are like 30
different things on the top of some of the pages and I have to scroll a fair bit to get to the actual
info."* **Those numbers have been fixed; the *rule* is what survives — corrected 2026-09-03, because the
banner still quoted the 2026-08-08 pre-fix measurements ("~15 consecutive alert/note/badge blocks, then 9
stacked analysis cards, before the frames table starts at line ~1339 of 1481", "the sidebar is 15 flat
links") long after slices (a)–(e) shipped 08-13→16.** Today `routes/Target.tsx` carries **one**
`NoticeBoard` and the nav is **18 links in 5 groups** (`frontend/src/nav.ts`), and the running-app probe
re-measured at v0.338.1 puts the tallest page — still the Target page — at **3,014 px on a phone**, down
from 14,584 px on the worst page before the slices. **So do NOT open a speculative IA slice**: two dogfood
passes four days and ~80 versions apart agree that nothing is stacked badly and the worst page moved 21 px
(see `docs/IMPROVEMENTS.md`, search **"DOGFOOD BASELINE"** for both measurements). What is still live is the
*standing rule* below — when you add a feature, put it inside the existing grouping rather than appending
one more always-on banner — plus the two named leftovers, the header row and the ten-item share menu.
**The hard constraint is the owner's own: NOTHING MAY BE
REMOVED — "don't get rid of features, just move them to a more organized layout."** This is pure
regrouping (consolidate the banner wall behind one prioritised "N more notes" disclosure, tab/grid the
stacked cards, put the picture and frames table above the fold, group the nav). **Adding NEW PAGES is
explicitly allowed** — *"even if they need to add pages, that is fine. I just want the organization to
be clean, simplistic, and make sense."* Splitting an overloaded page across focused **nested routes**
(`/library/<target>/insights`) usually beats cramming it back into one screen, and stays bookmarkable;
just don't over-fragment — one nameable purpose per page, routine things ≤1 click away. **If a *measured*
page ever needs another slice, take ONE per run**, state the before/after block counts in the commit, and
let the owner react between slices — but measure first with `scripts/agent-dogfood.sh`, because the last
two measurements both said not to. Full entry, measurements, slicing order and cautions:
`docs/IMPROVEMENTS.md` → "Friendliness (PRIORITY 3)"; search it for **"DOGFOOD BASELINE"** and for the IA
slices by name rather than reading from the top of the section. A verified bug still outranks it; feature-piling does not —
**prefer a slice of this over inventing another card**, and when you *do* add a feature, put it inside
the new grouping rather than appending one more always-on banner.

**📜 HISTORICAL (was "⚡ IMMEDIATE PRIORITY", 2026-07-30; demoted 2026-09-03 because it
is neither immediate nor a priority any more — it is a fixed bug's write-up, and a second
banner claiming to be front-of-queue only splits the queue). Kept for its root-cause
record, not as work.** The owner-reported mosaic
"multicolour grid" regression is FIXED (v0.225.0); its root cause was confirmed by repro
and measured. `analyze_proxy` measured sky noise as the MAD of the sky's *levels*, which
counts a mosaic's per-panel level/colour offsets (and any residual gradient) as grain — so a
deep, clean mosaic read as one of the noisiest images the app had seen (`sky_sigma` 0.0078 as
a single field → 0.0299 as a mosaic), fired `detail.chroma_denoise` at its full ceiling and lost
its sharpening. `sky_sigma` is now measured **locally** (MAD of adjacent-pixel differences), which
is blind to seams and gradients and agrees with the old number to within 3 % on structure-free
noise, so ordinary single-field stacks are unchanged. **One follow-up remains, and only if the
owner still sees a grid on v0.225.0:** bisect the rest of the v0.158→v0.220 colour chain (SCNR,
per-frame / final gradient flatten) on the synthetic mosaic scene now in
`tests/test_auto_noise_measure.py` — filed in `docs/IMPROVEMENTS.md`. *(The owner-requested
**Auto auto-crop toggle** this paragraph used to point at as "filed and unstarted" **shipped in
v0.226.0** — don't go looking for it. Refreshed 2026-08-04.)* Everything
below was the previously-drained queue —

that queue is DRAINED; every ⭐ item
this section used to list is now fixed and verified. Don't go looking for them: the
S30 wrong-FOV solves, the ASTAP ladder, the faint-field stack-then-solve bootstrap and
the Seestar ingest/upgrade-heal shipped in v0.184–v0.210; the whole **one-click Auto
colour/brightness breakage** chain then shipped in v0.210.5–v0.213.0 — SCNR's magenta
sky (−11.5% → −1.2%), the auto-contrast curve lifting the whole sky (+42% → gated off
on sky-dominated frames), the **final** gradient pass's starved object mask (colour
spread 34.3 → 3.9 ADU), and the **per-frame** flatten's identical starved mask, which
was the upstream half (honest-path stack tilt Σ|R/G/B| 102.7 → 18.1 ADU, and the
finished Auto picture's brightness tilt +64% → +11% of sky). The numeric-`null`
stack-defaults poisoning, the 2000-frame truncation, and all five listed click-path
bugs are fixed too.

**So what's front-of-queue now? (re-checked 2026-09-03 — the 2026-07 answer below it
had gone stale twice over.)** Read the **Bugs** section of `docs/IMPROVEMENTS.md`
yourself and believe *it*, not this paragraph: the whole A1–A10 external-audit batch
has since been filed there and shipped, so any list of "the open ones" written here
rots within days. What has stayed true across three refreshes is the *shape* of what
is left: the entries still open are **gated** on something an agent cannot supply from
the repo — real elongated-target data, a legacy library shape the owner doesn't have,
an external binary — or are deliberate stand-downs with the measurement already
recorded. **Read the gate, or the stand-down, before starting one; do not blind-flip a
threshold or a default on the on-by-default hot path, and do not re-litigate a
stand-down that carries numbers.** With the bug list in that state, work the **Current
focus** list immediately below — a bug *you* verify yourself still outranks all of it.
And **grep before you build**: the Ideas list has repeatedly carried items that were
already shipped, and several "new" features turn out to be copy tweaks on machinery
that already exists.


**Current focus (2026-07, set by the owner; the editor claim corrected 2026-09-03).**
The editor's *traced* bug backlog is drained and adversarial re-audits mostly come
back clean — but **do not read that as "well-hardened"**: the 2026-09-02 external
audit found two real editor defects (A1 and A2) that had survived exactly such
re-audits, which is why priority 1 is re-opened at the top of this section. What
follows is about *marginal* value, not about the editor being finished: it no
longer needs feature-piling, and if a *real* editor regression appears, fixing it
still comes first. With that said, the highest marginal value is in:
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
A healthy run lands **~2–4 tasks** (more if small, fewer if one is large — a
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
8. Add any new ideas you found to `docs/IMPROVEMENTS.md` (Scout only — §4), then
   **merge your green work into the default branch yourself** and clean up (§8).
   This project is zero-touch: no human reviews or merges, so shipping = merging.
   Then stop.

**The three-file rule — where writing goes (added 2026-09-04; R2).**
`docs/IMPROVEMENTS.md` is the **working list only**, and a run must leave it *no
longer than it found it* unless it is filing a verified bug. It grows ~100 lines
per merged PR and is already far past what any agent can read in a run, so a stale
entry survives by default and gets re-picked — several runs have been spent
rebuilding something that shipped weeks earlier.

- **`docs/IMPROVEMENTS.md`** — open bugs, live claims, open ideas. "Bugs (fix these
  first)" contains **open bugs and nothing else**.
- **`docs/SHIPPED.md`** — when an item ships or is closed, **cut the whole entry**
  and append it there (newest first, headed by version + date); leave a one-line
  `✅ v0.xxx.y <what>` under "Shipped" in the backlog. Grep this file before filing
  an idea.
- **`docs/PROCESS-NOTES.md`** — process notes, collision diaries and QA sweep
  records (**including clean ones**), one dated block each. **Never** into a
  priority section: the top entry of "Bugs (fix these first)" has more than once
  been a clean-sweep record, which is what every triaging agent reads first.

Delete an "In progress" claim when you release it — that section is a claim board,
not a diary.

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

**Only the Scout adds ideas, and only after checking the idea is not already filed
or shipped** (grep `docs/IMPROVEMENTS.md` for the idea's key nouns before writing
a line — this list has repeatedly carried items that had already shipped). A
**Builder** files only two things: a bug it verified itself, and a lead it could
not finish. It does not spend a run inventing features.

*(Corrected 2026-09-04 — R3. This section used to tell **every** run to "aim to add
at least a couple of well-reasoned ideas", which contradicted the Builder role text
above it and made idea supply the thing the backlog had most of: **26 new idea
entries were added on 08-27 alone**, and 49 of the 162 filed were still open against
193 open priority items. Supply was never the constraint; a Builder's hour is. The
§12 checklist line that mandated the same thing is gone with it.)*

When the Scout does add one, record it with a why, a rough size, and which pillar
it serves. Here's how to find good ones.

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

Lint is not enforced in CI yet, but check before claiming quality-bar work:
`ruff check .` has pre-existing debt — don't let it block unrelated work, and
don't add to it. Put temp/scratch files under the session scratchpad, never in
the repo.

> Tip: **`scripts/agent-setup.sh` does all of the above idempotently** — run it at
> the start of every run (`source scripts/agent-setup.sh`) instead of hand-typing
> the steps. Wiring it into a `SessionStart` hook makes every run start green with
> no setup tax.

> Tip: **`scripts/agent-dogfood.sh` boots a real app with real data** for the §2
> big-picture pass — scratch data root, the bundled sample loaded and stacked,
> then Playwright full-page screenshots at 1440 px **and** 420 px plus an
> overflow probe. Use it instead of re-reading route files: the bugs that survive
> code-level audits are the ones only a running app shows. `--serve` leaves it up
> to poke by hand; `--no-probe` skips the browser half. Everything lands in a
> scratch dir, never the repo. Whatever it finds still needs a real regression
> test in the suite — it is a finder, not a test.

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
2. Commit each task as its own well-described commit. **The subject must name the
   item's key nouns *and at least one code identifier*** — a function, module or
   setting — so the next agent's "grep the log before you build" (§11) actually
   finds it. A headline alone is not a subject. *(Added 2026-09-04: only **4 of 250**
   commit subjects contained a code identifier, which is why that grep keeps missing
   work that had already shipped.)* End every commit message with the repo's trailer
   convention (a `Co-Authored-By:` line; never put any model identifier in commits,
   code, or logs). Push after each task (`git push -u origin <branch>`); retry
   transient network errors with backoff.
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

- **🔒 THE INCOMING FOLDER IS STRICTLY READ-ONLY. THE APP MUST NEVER DELETE, MOVE,
  RENAME, TRUNCATE, OR OVERWRITE ANYTHING INSIDE IT.** *(Owner requirement,
  2026-08-07 — the single most important rule in this file.)* The owner's **raw
  subs exist in `incoming/` and NOWHERE ELSE — there is no backup and no second
  copy.** If the app deletes a file there, the owner's data is gone forever and
  no amount of re-stacking brings it back. Therefore:
  - The **only** permitted operations on any path under
    `Settings.resolved_incoming_dir` are **read** and **create-new** (the upload
    endpoints may *add* files; the scanner/ingest may only *read*).
  - **Ingest copies, it never moves** (`shutil.copy2` in `seestack/io/ingest.py`)
    — that is deliberate and load-bearing. **Never** "optimise" it into a
    `shutil.move`, `os.rename`, `Path.rename`, or a hardlink-plus-unlink, and
    never add a "free up space by removing ingested originals" feature, however
    well-intentioned or opt-in.
  - **No cleanup, prune, tidy, dedupe, archive, quarantine, "move processed
    files", or "delete after successful stack" behaviour may ever target
    `incoming/`** — not by default, not behind a confirmation, not behind a
    setting. Cache/thumb/output cleanup stays inside the library's own
    `targets/` tree and the app's result stores, which is where every existing
    `unlink`/`rmtree` is correctly scoped today (audited 2026-08-07: ingest
    copies, and no destructive call resolves into `incoming/`).
  - If a future feature seems to *need* to remove something from `incoming/`,
    that is **"needs owner sign-off"** — file it, do not build it.

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

Multiple agents overlap in time. Git serialises merges and containers are isolated,
so file races are not the risk. **The risk is two Builders choosing the same item in
the same minute:** this has cost at least twelve items across ten collision events
(2026-08-26 → 09-02), and every one happened while two Builder runs overlapped.
Claiming an item in `docs/IMPROVEMENTS.md` is a **publication, not a lock**, and has
not prevented a single one — by the time you claim, the other run already chose.

**Choose so that two simultaneous runs rarely pick the same thing.** Within the
highest-priority section that has open work, pick **uniformly at random among the top
four open, unclaimed entries** (a ⭐ entry is always taken first; do not mark anything
⭐ that is not urgent). Then, *before writing a line*: `git fetch origin main`, and
`git log --oneline origin/main -30` grepped for the item's code nouns. If it is on
`main`, stop and pick again; if it is claimed on a branch pushed within the last two
hours, pick the next.

**While working**
- Read recent `git log` and open PRs/branches first; skip topics already in flight.
- **Re-`git fetch origin main` before starting *each* task, not just at start of
  run.** Claiming an item in `docs/IMPROVEMENTS.md` is a *publication*, not a
  lock: it only helps agents who look again. Two Builders have independently
  built the same item twice in one hour despite both claiming early — a fetch
  between tasks costs a second and catches it before a line is written.
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

Per task (repeat ~2–4×, or fewer if large):
[ ] git fetch origin main FIRST — another agent may have shipped this task while
    you worked on the last one (the merge commits show at least ten such
    collisions, twelve duplicated items; §11)
[ ] picked/invented ONE task (§3 decision rule or §4 ideation); marked In progress
[ ] implemented across engine/webapp/frontend as needed
[ ] upgrade-safe: config loads, DB migrates, layout/defaults/API unchanged (§9)
[ ] added/updated tests; python + (if FE touched) tsc/vitest/vite build green
[ ] version bumped; IMPROVEMENTS.md updated (item → Shipped)
[ ] committed (independently green) and pushed

End of run:
[ ] Scout only: any new idea grep-checked against the backlog first (§4); a
    Builder files only verified bugs and unfinished leads
[ ] synced branch with latest default; full suite still re-run and green (§11)
[ ] version set by bumping the LATEST main; IMPROVEMENTS.md conflicts kept as a
    union (never drop another agent's entry) (§11)
[ ] merged into main yourself (PR-merge preferred so the branch auto-deletes);
    topic branch deleted/gone; only main + truly-in-progress branches remain
```
