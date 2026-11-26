# AstroStack process audit — is the autonomous setup producing meaningful progress?

Audit date 2026-11-26, `main` at v0.511.5 (`5263bb61`). Read-only; nothing in the repo was changed.

**Verdict: the owner is right.** Over the last 60 days 42 % of everything merged changed no code, another 20 % fixed
edge cases found on synthetic data, and since 2026-11-20 the app has effectively stopped moving (35 of 39 merges are
"nothing to do" records) while his own highest-severity bug sits parked behind a reporting channel that went silent
45 days ago.

## Method and one correction to the brief

- The local clone is **shallow**: its history starts 2026-10-21. The "307 first-parent merges in 60 days" figure is
  really 307 merges in **36 days**. The true 60-day figure (2026-09-27 → 11-26) is **572 merged PRs**, taken from
  `gh api repos/.../pulls?state=all` (1,537 PRs, 1,534 merged).
- Classification (Q1) is by PR title, cross-checked against the `Shipped` one-liners and `docs/SHIPPED.md` for owner
  markers. Rules and per-PR labels: `scratchpad/audit/process/classify.py`, `overrides.txt`, `labeled.tsv`.
- Line/size numbers: `git ls-files | wc -l` at HEAD; historical sizes from `gh api .../git/trees/<sha>?recursive=1`
  (blob bytes) at four dates. CI numbers: `actions/workflows/ci.yml/runs` (600 push runs on `main` since 09-19).
- Not done: no pytest, no dogfood, test bodies were sampled by name only. (c)/(d) is a judgement call, explained below.

## 1. What actually shipped (60 days, 572 merges)

| Category | 60 days | % | last 30 days (269) | % |
|---|---|---|---|---|
| (a) owner-requested feature/fix | 39 | 6.8 % | 18 | 6.7 % |
| (b) agent-chosen feature/polish | 25 | 4.4 % | 19 | 7.1 % |
| (c) fix he would plausibly hit | 109 | 19.1 % | 30 | 11.2 % |
| (d) synthetic-only edge case | 114 | 19.9 % | 49 | 18.2 % |
| (e) docs only / nothing to do / clean sweep | 238 | 41.6 % | 136 | 50.6 % |
| (f) test / infra / process | 47 | 8.2 % | 17 | 6.3 % |

Per ISO week (count, % of that week):

| Week | n | a | b | c | d | e | f |
|---|---|---|---|---|---|---|---|
| W39 (2 days) | 16 | 4 (25) | 2 (12) | 3 (18) | 0 | 6 (37) | 1 (6) |
| W40 | 73 | 6 (8) | 3 (4) | 21 (28) | 13 (17) | 20 (27) | 10 (13) |
| W41 | 47 | 0 | 0 | 17 (36) | 10 (21) | 11 (23) | 9 (19) |
| W42 | 54 | 9 (16) | 0 | 13 (24) | 6 (11) | 17 (31) | 9 (16) |
| W43 | 108 | 2 (1) | 1 (0) | 24 (22) | 34 (31) | 46 (42) | 1 (0) |
| W44 | 53 | 5 (9) | 3 (5) | 9 (16) | 17 (32) | 18 (33) | 1 (1) |
| W45 | 62 | 0 | 14 (22) | 7 (11) | 11 (17) | 27 (43) | 3 (4) |
| W46 | 84 | 1 (1) | 1 (1) | 13 (15) | 18 (21) | 41 (48) | 10 (11) |
| W47 | 48 | 12 (25) | 1 (2) | 2 (4) | 3 (6) | 28 (58) | 2 (4) |
| W48 (3 days) | 27 | 0 | 0 | 0 | 2 (7) | 24 (88) | 1 (3) |

Other measures of the same thing:

- **Feature rate collapsed.** Minor ("feature") versions named in PR titles: July 122, Aug 47, Sept 156, **Oct 14,
  Nov 6**. The 60 days moved the app from 0.479 to 0.511: 32 feature versions against roughly 290 patch versions.
- **Almost every real feature in the window was one he asked for in words**: Seestar page (4 slices), Settings
  redesign (5), declutter (8), progression reel (3), one-click update, auto-drizzle (2), Moon/Sun drizzle, recipe
  carry-over, ragged-border fix (5), diagnostics mechanism. When he asks, it ships in 1–3 days. When he does not, the
  machine produces (d) and (e).
- Of the 39 (a) merges, 8 are the declutter slices — repairing clutter the process itself created (the Stack form had
  **40 always-on alerts**, the Target page 30 clutter items).
- 11 further "diagnostic" merges (filed under f) were built for his bugs and have delivered nothing yet (Q2).
- In the 36 days of local history: 158 of 306 merges touched app code; median app change **56 lines**, with 88 lines of
  tests and 39 lines of docs beside it; 49 app merges changed ≤ 30 lines. Totals: app +13,994 / tests +17,660 /
  docs +20,638 lines.

**How (c) and (d) were separated.** (c) = the trigger is his normal shape (S30, mosaic, thousands of subs, the
twin-registered folders of #878, editor/export on a mosaic, Moon & Sun) *and* the symptom is a wrong picture, a lost
frame, a crash or a wrong statement on a primary screen; every observer-issue fix is (c). (d) = the trigger needs
hostile or rare input (NaN in a request body, non-UTF-8 names, a hung decoder, colliding target names), or the symptom
is a number/wording nuance on a secondary card the agents invented (life list, "It's back", week plan, Compare, deep-sky
wall), or phone-width/keyboard polish with no evidence he uses either. Roughly half of (d) is real but minor; a
stricter reader could move ~20 from (c) to (d) (editor memory-copy and North-up chains), a kinder one ~15 the other way.
The shape of the table does not change.

**Ten concrete (d) examples**

| PR | What | Why (d) |
|---|---|---|
| #1562 v0.511.5 | target whose display name equals another's folder name | needs two colliding names |
| #1193/#1194/#1195/#1198 | NaN/Infinity in recipe params, query params, JSON ints | four merges; no browser sends these |
| #1437 v0.506.18 | sub file name not valid UTF-8 | a Seestar never writes one |
| #1445 v0.506.21 | future-dated sub | source clock ahead; "left for an owner report" since August |
| #1456 v0.506.25 | unknown `/api` GET answers 404 not the SPA shell | invisible to a user |
| #1297 v0.503.8 | hung ffmpeg decoder killed after a stall | stub-binary scenario |
| #1288 v0.503.2 | Channel combine intro missing a space | in a section AGENTS.md marks "do not invest" |
| #1305 v0.503.13 | desktop Library dialog's solved count | he runs the web app |
| #1350 v0.505.8 | "It's back" names the deepest returning target per part | nuance in an agent-invented card |
| #1366/#1368/#1365 | arrow-key / Enter / Space on calendar, dividers, navigator | keyboard a11y, never requested |

## 2. Idle runs and what is blocked

- **"Nothing ungated" Builder runs: 35** in 60 days; **27 of them since 2026-11-21** (3, 2, 5, 7, 7, 2 per day).
  A further 59 Builder merges are "no app change / dogfood CLEAN". Builder docs-only records: 12 in October, **86 in
  November**.
- Each idle run still opens a PR, merges it, and triggers the full CI twice (PR + push, no `paths-ignore`): ~47–55
  minutes each. 238 docs-only merges ≈ **350+ runner-hours** in 60 days to record that nothing happened.
- The Builder is idle *by rule*: it "does not invent features", may not start a gated entry, and every open Bugs
  entry is gated.

**What is blocked, and on what**

| Item | Waiting since | Blocked on | Real blocker? |
|---|---|---|---|
| ⭐ 🔴 Sensor colour pattern (blotches on ~25 % of his pictures; owner-reported 11-01, measured on 105 targets) | HOLD 11-09 (17 d) | diagnostic `sensor_pattern_by_temperature` v2 | **No.** The spec is already opt-in, default off, self-gated on r ≥ 0.5 / ratio ≥ 2. Temperature only decides one master vs per-temperature masters; build it binned by temperature and let the on-device gate decide |
| Dark ring inside ragged border (part 4 of his 10-28 report) | 10-30 (27 d) | `sky_falloff` v3 | Partly. Fix can ship self-gating on the measured fall-off |
| Un-located mosaic panel is silent (Scout 10-19) | 38 d | `mosaic_panel_hints` v2 | No — code can branch on hint-cluster count at runtime |
| Streak-guard second half (Scout 11-19) | 7 d | same diagnostic | same |
| #878 headline over-count | 09-13 (74 d) | `twin_target_overcount` v1 | Low value either way |
| Filter-night card (idea) | 11-09 | `filter_card_values` v2 | Feature can simply hide when the card is absent |
| Skip `.recycle/`, `.Trash-*/`, `.zfs/` at scan (sign-off 19) | 11-03 (23 d) | owner yes/no | **No.** He answered the identical question for `batch_stack_tmp` with "yes, skip"; skipped folders already have "bring it in" |
| Sign-off 3 "still see a multicolour grid?" | 09-08 (79 d) | owner | Stale; superseded by the ⭐ pattern entry — close it |
| Sign-off 5 Maintenance screenshot (gates three image-quality items) | ≥ 09-08 | owner screenshot | Should be a diagnostic/API field, not a screenshot |
| Sign-off 4, 6, 11, 12, 13 (a `.wcs` sidecar, M42 core, edge-on galaxy, faint target, heavy nebulosity) | ≥ 09-08 | owner files/names | All are "find an example in his library" — an on-device diagnostic's job |
| Sign-off 2 (flip Auto-stack himself), 8 (un-ingested subs?) | ≥ 09-08 | owner | Real, but low urgency |
| Issues #878, #880, #903, #1015 | 58–74 d | "owner-gated" | Re-checked by 30+ runs (FOCUS lists them by name), acted on by none |
| 9 LEAD / ⚪ / DECIDE entries in Bugs (lines 211–610) | 09-09 … 10-18 | "owner/observer measurement" | Mostly should be closed as won't-fix |

**The single biggest stuck thing** is the ⭐ sensor-pattern fix: the only open item the owner reported himself, rated
high severity, measured on his own library, with a complete spec.

**Why the diagnostics channel has delivered nothing.** The chain is: owner updates past v0.506 → app runs the
diagnostics → the NAS observer reads `/api/diagnostics` → observer files a GitHub issue → Scout reads it. The
**observer's last issue or comment of any kind is dated 2026-10-12** (29 issues between 09-13 and 10-12, then
nothing). Forty-plus runs have written "inbox unchanged … no `Diagnostic result:`" without one concluding the
reporter is dead. The observer's prompt also lives on the NAS, so teaching it to file diagnostic results needs the
owner. Last known deployed version is v0.492.43 (from #1015, 10-12); nobody knows whether he is on v0.506+.

**A design that does not depend on the observer or its prompt**

1. **Gate in code, not in the backlog.** A diagnostic's verdict is consumed by the app on the device: the fix ships
   dormant and switches itself on (or offers itself) when the measurement on his library clears the bar. No round trip.
2. **A "Report for the developer" card** (Settings → Maintenance): shows the stored diagnostics JSON (already
   privacy-checked by `check_result_is_safe`), version, and a Copy button. The owner pastes it into any session, or
   clicks a prefilled GitHub "new issue" link in his own browser (the app itself makes no network call).
3. **A liveness rule:** if the newest observer activity is older than 7 days, that is the ⭐ item in FOCUS and the
   first line of the next message to the owner — not a line to re-copy.

## 3. Is the Scout rotation generating low-value work?

- "Daily" Scout: **138 Scout run records in 60 days** (2.3/day; 19, 15 and 14 Scout PRs on 10-21, 10-20, 11-11).
- 143 merged PRs mention a sweep: 51 are clean-sweep records; the rest file or fix a sweep bug.
- Origin of the 314 version entries shipped since v0.479.2 (IMPROVEMENTS `Shipped` one-liners): **Scout sweep 45,
  dogfood 33, observer issue 19, owner 6 entries (39 merges), other agent reading 211**.
- Of 34 fix merges whose title names a sweep: **24 are (d)**, 5 (c), 4 (f), 1 (a). By sweep: (3) stub-binary and (4)
  routers are almost entirely (d) — NaN bodies, cache headers, 404 shapes, hung decoders. (1) parity and (2) per-panel
  find things on his shape, but increasingly inside agent-invented cards.
- Severity of what the rotation now finds: recent run headings carry 🟡, 🟡, 🟢, one 🟠. Nothing 🔴 since October.
- AGENTS.md demands each sweep "find a new angle"; angles are now "an ASTAP that is a wrapper script hitting the
  timeout" and "HEAD/Range on file-serving GETs".

**Incentives.** Yes, they produce churn: a Scout run that files nothing looks like it did nothing; a filed 🟡 is the
only thing that un-idles the Builder; every fix gets its own PR, version, SHIPPED entry and FOCUS rewrite. The loop
Scout-files → Builder-fixes → Builder-"reads CLEAN" → Scout-sweeps is self-sustaining and never touches the owner.
The observer, while alive, was far better value: 19 issues, all real-library, almost all (c).

## 4. Cost of the paperwork

| Start-of-run reading | Words | Bytes | ≈ tokens |
|---|---|---|---|
| AGENTS.md | 5,231 | 34.6 KB | 9k |
| docs/FOCUS.md | 1,711 | 12.3 KB | 3k |
| docs/IMPROVEMENTS.md | 177,876 | 1,206 KB | 300k |
| docs/AGENT-ENVIRONMENT.md | 7,232 | 43.1 KB | 11k |
| **Total** | **192,050** | **1,296 KB** | **≈ 320k** |

- The prompts say "read docs/IMPROVEMENTS.md". It does not fit in a context window. **77 % of it (136,639 words,
  1,459 lines) is the `Shipped` list**; the open part is ~41k words.
- `Shipped` "one-liners": 299 entries, median 54 words, mean 113, **81 over 100 words, 37 over 300, max 556**.
- Ideas: 78 entries, median 250 words (max 4,432); 58 dated July–September, one from November; 33 mention a gate.
- Bugs: 20 entries in 530 lines (7,969 words); one is actionable.
- FOCUS.md ("short on purpose") is 12 KB; one sentence lists 30 run IDs that re-checked the inbox.
- Per merge (36-day window): SHIPPED +15 lines, PROCESS-NOTES +9, IMPROVEMENTS +4, FOCUS +3 ≈ **31 doc lines per
  merge**, 39 median beside a 56-line code change. All docs: 1.7 MB (07-29) → 6.8 MB (09-27) → 9.7 MB (11-26).
  SHIPPED.md is 45,617 lines / 3.7 MB, PROCESS-NOTES 17,138 lines / 1.5 MB (ceiling 18,000 — about to trip).
- **Is the docs-budget test working?** Mechanically yes: IMPROVEMENTS.md is flat at ~1,177 KB since October and
  archives exist. But it caps growth at an already-unreadable size, and pushed the bloat sideways into SHIPPED and
  PROCESS-NOTES. It measures lines, not usefulness.

## 5. Tests and CI

| | Count |
|---|---|
| Python `def test_` | 7,677 (suite reports 9,003 passed with parametrisation) |
| Frontend `it(`/`test(` | 5,006 in 313 files |
| Test lines : app lines | Python 174,583 : 120,559 (**1.45×**); frontend 69,284 : 65,727 (1.05×); overall **1.31×** |
| CI on `main`, median wall time | Sept 36 min → Oct 44 → **Nov 48** (p90 54); Python job alone ~47 min (serial, no xdist) |
| CI hours on `main` pushes since 09-19 | 433 h (PR runs roughly double it) |
| Non-green `main` runs | 22 of 600 (16 failures; five in a row on 11-11, two on 11-24) |
| New tests in 36 days | 822 (537 py, 285 fe) for 158 app merges ≈ 5 per change |

- **Per run:** baseline suite (~11 min with xdist), suite per task, suite again after merging `main`, then CI. An
  idle run pays the baseline to write one line.
- **Sample of 24 recently added tests (by name):** ~14 pin behaviour a user could see ("a hand-shaped curve is not
  replaced", "tonight and the week plan agree on the dark window"); ~7 pin exact wording or which sentence appears
  ("the offer names what it repairs rather than pointing at it", "says a restart cut off didn't finish, not that it
  never ran"); ~3 pin internals or the dogfood tool. The frontend has 2,303 `getByText`-style assertions, so copy is
  heavily frozen: rewording a page for clarity breaks tests, which discourages exactly the simplification he wants.
- **Date sensitivity:** 9 test files call `date.today()`/`datetime.now()` (`test_plan`, `test_year_recap`,
  `test_activity_calendar`, `test_target_live_session`, …) and nothing freezes time globally. The planner tests are
  the obvious Moon/season coincidence risk. Recommend one autouse fixed-clock fixture.
- 4,884-line `test_editor.py`, 4,308-line `Editor.test.tsx`: the tests are now larger than the things they test.

## 6. Code size and shape

| Area | Lines (HEAD) | Size 07-29 | 09-27 | 10-27 | 11-26 |
|---|---|---|---|---|---|
| seestack (engine) | 72,902 | 1,225 KB | 2,775 | 3,285 | 3,440 |
| webapp | 47,657 | 603 | 1,793 | 2,107 | 2,251 |
| frontend src (350 files) | 65,727 | 983 | 2,602 | 2,895 | 3,020 |
| Python tests (545 files) | 174,583 | 1,643 | 5,629 | 7,122 | 7,570 |
| frontend tests | 69,284 | 758 | 2,594 | 2,883 | 3,040 |

App code +21 % in 60 days, **×3.1 in 120 days**; tests +29 % / ×4.4.

- Largest files: `webapp/pipeline.py` 6,079; `webapp/routers/stack.py` 5,793; `seestack/stack/stacker.py` 5,474;
  `frontend/src/api/client.ts` 5,097; `seestack/io/project.py` 3,730; `webapp/routers/editor.py` 3,351;
  `Editor.tsx` 3,254; `seestack/nightplan.py` 3,212; `Jobs.tsx` 2,332.
- **258 API routes** (171 GET, 64 POST, 11 DELETE, 7 PUT, 3 PATCH, 2 app-level) in 32 router modules.
- **27 frontend pages**, 245 component source files, **47 Settings fields, 43 StackOptions fields**, 7 editor op modules.
- The owner's actual journey (drop → stack → edit → export) uses perhaps 6 of the 27 pages.

**Yes, surface is accreting faster than one person can use it** — mostly before this window (pages went 20 → 27
between July and September). The last 60 days were spent paying interest on it: about half of (d) is bugs inside
these features.

**Fifteen most elaborate things he did not ask for** (app lines / test lines):

| Feature | App | Tests |
|---|---|---|
| Tonight planner + "Plan my week" + "It's back" (`nightplan`) | 4,306 | 5,996 |
| Life list + card | 1,686 | 1,064 |
| Session recap ("Last night") | 1,621 | 2,861 |
| Universe map | 954 | 794 |
| Year recap ("Your year") | 936 | 557 |
| Live session page | 828 | 1,116 |
| Glossary | 637 | 816 |
| Sky-so-far / sky marks | 629 | 629 |
| Wishlist | 592 | 631 |
| Imaging calendar (+ .ics export) | 577 | 1,565 |
| Show-and-tell | 444 | 439 |
| Wallpaper export | 401 | 702 |
| Print export | 360 | 864 |
| Cover nudge / restored nudge | 337 | 295 |
| Portfolio, montage, nameplate, keepsake, share card, light-travel | ~1,100 | ~2,160 |

Also unrequested: Adaptive-Auto "taste" chips (ten-plus fix merges in October), Compare, target-difficulty, goals.

## 7. Stable channel lag

- Simulated the workflow against real CI results for every day since 09-27: it reproduces today's `stable`
  (`c655d375`, 11-21). **`stable` advanced every single day; it was never stuck.** All 60 workflow runs succeeded.
- Time from merge to `stable`: **median 3.56 days, min 3.0, max 4.3** (549 commits).
- So yes, he is always 3–4 days behind `main` by design, plus however long until he presses Update. That is the larger
  gap: the last deployed version anyone recorded is v0.492.43 on 10-12; on 09-29 he was 33 minor versions behind.
- Consequences: an owner-asked fix cannot reach him in under 3 days even when it is a one-liner; diagnostics were
  revised three times (v1 → v3) inside the soak, so "before it reached stable" became a design constraint; and with
  ~10 merges a day, each update is an unreadable pile of ~35 versions with no "what changed for you" summary.
- The soak's own justification (fix-the-fix chains close within 3 days) is an argument for releasing less often, not
  for trailing by three days.

## 8. Recommendations

### Three root causes

1. **The queue is fed by a synthetic bug-finder, not by the owner or his data.** The only real-data channel died on
   10-12 unnoticed, and every item that matters to him is parked behind it.
2. **The rules reward small and safe.** Gated → don't start; the Builder may not choose features; one slice, one PR,
   one version per fix. The one large, valuable job (sensor pattern, size L, hot path) is the one the rules park.
3. **Surface and paperwork outgrew the mission.** 27 pages, 258 routes, 1.3× tests, 9.7 MB of process docs, 48-minute
   CI: every change is expensive, and half the bugs found are in features nobody asked for.

### Changes, in priority order

1. **Un-park the owner's bug today.** Build the sensor-pattern master (opt-in, self-gating on device). Adopt "gate in
   code" for the dark ring and the two mosaic-hint entries. Auto-resolve sign-off 19 as "yes, skip, recoverable".
2. **Replace the rotation with owner themes.** `docs/ROADMAP.md`: at most three themes in the owner's words. The
   Builder works the top theme in large slices. Scout sweeps drop to one a week, file only 🟠+ on owner-shaped data,
   and batch everything smaller into one monthly hardening PR.
3. **Idle runs write nothing.** No PR, no commit, no FOCUS line. Drop the Builder to twice a day; add `paths-ignore`
   for docs-only changes in `ci.yml`; run pytest with xdist in CI.
4. **Weekly releases with plain-language notes.** One release a week, version bumped per release, a "What's new"
   card of ≤ 5 bullets. Soak 1 day; an owner-asked fix may be fast-tracked by `workflow_dispatch`.
5. **Cut the docs to what a run can read.** IMPROVEMENTS.md ≤ 300 lines (Now / Next / Waiting on owner ≤ 5), no
   `Shipped` section (git history and release notes are the record), PROCESS-NOTES frozen to the archive, AGENTS.md
   ≤ 250 lines. Replace the line-count budget test with those caps.
6. **A feature census.** Count page visits locally (shown in the developer report), then ask him which of the ~20
   unrequested pages he wants kept on the menu; fold the rest behind one "Extras" page (nothing removed) and freeze
   them: no sweeps, no polish, fix only on his report.
7. **Liveness of the feedback loop is a first-class item**: observer silent > 7 days, or deployed version unknown or
   > 14 days old, goes to the top of the owner message.
8. **Tests:** fixed clock fixture; stop asserting full sentences in the frontend (assert test ids / roles); no new
   test for a wording change.

### What the owner should be asked (one message, five questions)

1. Which three things do you most want better over the next month? (suggest: blotch removal, simpler screens, Auto
   quality on mosaics)
2. Is the NAS observer still running? If it is gone, may the app show a "copy this report" card instead?
3. Which version are you on, and are you happy with one release a week with a short "what's new"?
4. May we tuck the extras (year recap, life list, universe map, wishlist, planner, …) behind one "Extras" page?
5. Skip recycle-bin and hidden folders when scanning? (default: yes)

### Draft replacement text — AGENTS.md, "Agent roles"

```
## Agent roles — Builder & Scout

The test for every piece of work: **would the owner notice it on his next clear night or next edit?**
If not, it waits for the monthly hardening batch or is not done.

- **Builder (twice a day).** Works the top open theme in `docs/ROADMAP.md`, in the largest slice it can
  finish green. Order: (1) anything the owner reported or asked for; (2) the top theme; (3) a 🟠/🔴 bug
  filed with a repro on owner-shaped data. It may design and build within a theme without further
  sign-off. If none of the three has work, it **stops without writing anything** — no PR, no commit,
  no log line.
- **Scout (daily, short).** (1) Feedback loop: read open issues and any developer report the owner has
  pasted; record the deployed version and the date of the last observer activity. If the observer has
  been silent 7 days, or the deployed version is unknown or over 14 days old, that is the first line of
  `docs/FOCUS.md` under "Ask the owner". (2) Dogfood the current theme as the owner (mosaic, big canvas).
  (3) **Once a week only**, one adversarial sweep. File a bug only if it is 🟠 or worse *and* triggers on
  data shaped like his; anything smaller goes on one line in the "Hardening batch" list, fixed together
  once a month in a single PR.
- A sweep or dogfood pass that finds nothing writes nothing.

**Waiting on the owner's data is not a reason to stop.** If a fix depends on a measurement only his
library can give, ship the fix switched off together with the measurement, and let the app decide on
his machine (apply or offer it only when the measured evidence clears the bar written in the code).
Never park an owner-reported bug behind a report that must travel back through GitHub.
A yes/no question whose safe answer is obvious and reversible is answered by taking the safe default
and telling him in the release notes. "Waiting on owner" holds at most five questions, in plain words.
```

### Draft replacement text — AGENTS.md §2 "The run" and the three-file rule

```
## 2. The run

Start: `git fetch`; read `docs/ROADMAP.md`, `docs/FOCUS.md`, `docs/IMPROVEMENTS.md` (all three together
are under 500 lines — if they are not, shortening them is your first task); set up; confirm green.

Do one substantial thing, or nothing. One finished slice that the owner can see beats five patches.

**Records.** The commit message and the weekly release note are the record. There is no Shipped list,
no per-run diary and no clean-run entry. `docs/IMPROVEMENTS.md` has three sections and a hard cap of
300 lines: **Now** (≤ 5 entries, each ≤ 12 lines), **Next** (≤ 15 one-line entries), **Waiting on the
owner** (≤ 5 plain questions). An entry that ships is deleted. An idea older than 60 days that nobody
picked is deleted. `docs/PROCESS-NOTES.md` takes a note only when a rule in this file should change.

**Releases.** Agents merge to `main` as now, without bumping the version. Once a week the Scout cuts a
release: bumps the version, and writes `docs/RELEASES.md` — at most five bullets, in the owner's
language, of what he will notice — which the app shows as "What's new" after an update.
```

### What to delete from AGENTS.md

- The four-sweep rotation and "each sweep must find a new angle".
- "It does not invent features" (Builder) and "no per-run idea quota" (replace with themes).
- The three-file rule, the `Shipped` one-liner requirement, "QA sweep records (including clean ones)".
- Per-PR version bump (§5, §11 version-collision paragraphs go with it).
- "Take at most one layout slice per run".
- "Do not blind-flip … do not re-litigate a stand-down" as a blanket stop; keep it only for defaults on the hot path.
- The collision-avoidance choreography in §11 beyond "fetch before you start; an open PR is a claim" — with two
  Builder runs a day there is nothing to collide with.
- Keep unchanged: §9 upgrade safety, §10 guardrails (incoming read-only, identity, privacy), the public-repo rule.

### Draft Builder prompt

```
You are the Builder for AstroStack. You run unattended; nobody answers questions.

1. Read AGENTS.md, then docs/ROADMAP.md, docs/FOCUS.md and docs/IMPROVEMENTS.md.
2. `source scripts/agent-setup.sh`; confirm the suite is green (if red, that is your task).
3. Pick ONE piece of work, in this order: something the owner reported or asked for; the next slice
   of the top roadmap theme; a 🟠/🔴 bug with a repro on owner-shaped data.
4. Build the largest slice you can finish green today. If it needs a fact about his library, ship the
   measurement and the switched-off fix together and let the app decide on his machine.
5. Ask of the result: would he notice this? Say what he will notice in one plain sentence in the PR.
6. If there is nothing to do, stop. Do not open a PR, commit, or edit any doc.
```

### Draft Scout prompt

```
You are the Scout for AstroStack. You run unattended; nobody answers questions.

1. Read AGENTS.md, docs/ROADMAP.md, docs/FOCUS.md, docs/IMPROVEMENTS.md.
2. Feedback loop first: open issues, any pasted developer report, the deployed version, the date of
   the observer's last activity. If the loop is broken or stale, put that first under "Ask the owner".
3. Use the app as the owner on a mosaic at his scale, on whatever the current theme touches. Write
   down only what he would notice.
4. Mondays only: one adversarial sweep. File 🟠+ bugs with a repro; add anything smaller as one line
   to the hardening batch.
5. Mondays only: cut the weekly release and write ≤ 5 plain bullets in docs/RELEASES.md.
6. Keep IMPROVEMENTS.md under 300 lines and "Waiting on the owner" at five questions or fewer.
7. If nothing changed, write nothing and open no PR.
```
