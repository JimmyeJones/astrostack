# AstroStack UX audit, judged as the owner (v0.511.5, 2026-11-26)

Method: `scripts/agent-dogfood.sh --build --mosaic --editor --big --incoming-lag --serve` (port 8811, data root in scratch),
then my own Playwright pass at 1440x900 and 390x844 over 28 routes (metrics + fold/full PNGs), and a timed journey on the
2x2 mosaic: target page, stack form, stack, History, editor, Auto, op expand, export, PNG download, Gallery, phone nav and editor.
Screenshots: `.../scratchpad/audit/ux/shots/<page>-{desktop,phone}-{fold,full}.png`; journey: `.../audit/ux/journey2/`
(log `journey2/journey.log`); metrics: `shots/metrics-main.json`.
The dogfood library is 3 small sample targets, so lengths are a floor. The owner's 100 targets and thousands of subs make every list longer.

## 1. Verdict (5 lines)
1. The picture is not the hero. In the editor at 1440x900 the image starts at y=715 (185 px visible), under three explanatory cards. While you drag a Stretch slider (y≈1850) the image is off screen on desktop and on phone (img top −824 px).
2. Every page explains itself at length. Target, Dashboard, Stack and Editor each open with 2–3 paragraph notices (40–100 words each) before the thing he came for, so "busy" is now mostly prose, not cards.
3. The navigation is the clutter he sees first: 19 sidebar links in 5 groups, 6 of them "your pictures" variants. Settings and Glossary sit below the fold at 1440x900 inside an unmarked scroll area.
4. The clutter ratchet went down while the screen did not. Dashboard.tsx scores 0/0, but its import closure renders 24 card/note kinds and 16 `<Alert>` sites (it was 23+2 before). Target.tsx scores 17/0, its closure 32 kinds, 23 Alerts and 14 `alertNoticeNode` notices.
5. The engine journey works: stack 60 s, Auto 0.55 s, export 9.9 s, PNG 4.8 s, no console errors. The last ~10 Builder runs shipped nothing ("nothing ungated") because none of the structural UX work is in the backlog as buildable entries. That matches "meaningful updates have not been happening".

## 2. Per-page table
Counts are [above fold / total] on desktop. Length is in screens (desktop / phone). Shot paths are under `audit/ux/shots/`.

| Page | Purpose (one sentence) | Alerts | Cards | Buttons | Words | Length d/p | Top problems | Shot |
|---|---|---|---|---|---|---|---|---|
| Dashboard `/` | What needs me and what's new | 2/2 | 7/10 | 5/8 | 376 (828 phone) | 1.4–2.5 / 4.9 | 9 visible blocks, not 5. The incoming-lag note is 5 sentences. The ASTAP banner says it is "required before you can stack anything" right above 3 finished stacks. "Famous, easy targets" heads a list that opens with Heart Nebula, CHALLENGING, NEEDS 5x7 MOSAIC. The Tonight tab duplicates `/tonight`. | dashboard-desktop-full.png |
| Library | All targets, plus drop new files | 1/1 | 4/4 | 6 | 161 | 1.0 / 2.0 | Good. The upload box is always on top though uploads are rare. The merge offer is a big purple banner. | library-desktop-fold.png |
| Target (field) | This target's picture and what to do next | 3/3 | 2/7 | 9/24 | 619 | 2.4 / 4.0 | See the mosaic row. Phone takes 11.3 s to load. | target-field-* |
| Target (mosaic) | Same | 2/2 | 2/8 | 9/41 | 843 | 2.5 / 4.5 | 2 planning notices above the title. 6 header buttons, 2 of them primary ("Process target" and "Stack": which one?). A per-sub table with reject controls sits at top level. Preview, Notes, then 3 tabs of more cards. 41 API calls; idle took 8.8 s (18 s in the probe). `/plan/best-months` alone takes 7.2 s. Contradictory goals: "4 min of ~7 h" next to "9 panels ≈ 18 h". | target-mosaic-desktop-full.png |
| Stack form | Choose settings and start | 1/2 | 2/2 | 10/28 | 331 | 1.4 / 1.9 | Expert toggles at top level (Sigma κ, Min/max, Drizzle outlier rejection, Mono/filtered subs). Start stacking is below the fold (y=1209). The Advanced section opens to 43 inputs. A 100-word luminance-flatten paragraph says the default "leaves cyan cores and red halos". | stack-mosaic-desktop-full.png, journey/stack-advanced.png |
| Jobs | What's running and what happened | 1/2 | 4/4 | 4 | 455 | 1.2 / 2.7 | Done jobs still show the raw stage string "stack:Saving 1/1". Each result card is 3 lines of prose. | jobs-desktop-full.png |
| Editor | Make the picture beautiful and export it | 2/2 | 3/14 | 10/53 | 883 | 2.5 / 4.3 | Picture below the fold, not sticky (see verdict). An encyclopedia card, a framing card and "How's my stack?" sit above the picture. Planning advice ("bigger than this mosaic, 18 h") appears inside the editor. Export, Download PNG, Share JPEG and Print with a 100-word Drizzle lecture all sit at the bottom right. First paint 5.9–9.3 s. | editor-big-desktop-{fold,full}.png, journey2/editor-op-expanded.png |
| History | Every stack and edit of a target | 0 | 2 | 8 | 87 | 1.0 / 1.0 | 7 buttons per run (Edit note, Edit, Reuse, Compare, Save/share, About, Delete). | history-mosaic-* |
| Gallery | Browse all pictures | 0 | 3 | 9 | 567 | 1.0 / 1.8 | Overlaps Best, Library and Dashboard "Your pictures". | gallery-* |
| My best pictures | Ranked best | 0 | 3 | 1 | 97 | 1.0 / 1.4 | Ranks the 6-frame, 1 min single field #1 above two 21-frame mosaics under a "deepest, cleanest first" caption. | sheet1.png |
| Your sky, so far | Totals and sharing | 1 | 8/11 | 5 | 260 | 1.4 / 2.1 | Third copy of the totals (Dashboard tiles, Life list). | sky-so-far-* |
| Life list | Messier checklist | 0 | 15/27 | 15/29 | 414 | 1.7 / 3.7 | Fine as a nested tab. | life-list-* |
| Universe | 3D distance view | 0 | 1 | 0 | 76 | 1.0 | Novelty. Nest it. | universe-* |
| Tonight | What to shoot tonight | 0 | 5 | 1/13 | 450 | 2.1 / 5.0 | Clear. Duplicated on the Dashboard. | tonight-desktop-full.png |
| Sky Map | Sky with your pictures | 0 | 1 | 0 | 43 | 1.0 | Fine. | sky-* |
| Tonight, live | Live session view | 1 | 1 | 2 | 101 | 1.0 | Name clashes with "Tonight". | live-* |
| Telescope | Seestar status | 1 | 0 | 0 | 34 | 1.0 | Near-empty page with a top-level nav slot. | telescope-* |
| Moon & Sun | Video stacking | 0 | 1 | 0 | 109 | 1.0 | Niche for this owner. Nest it under Tools. | moon-sun-* |
| Calibration | Darks and flats | 2 | 2 | 1 | 199 | 1.0 / 1.3 | OK. Rare task. | calibration-* |
| Channel combine | Mono/LRGB (deprioritised) | 1 | 2 | 9 | 101 | 1.0 | A deprioritised pro feature holds a top-level nav slot. | combine-* |
| Storage / Logs / Glossary | Housekeeping | 0 | 1–4 | 1–48 | 186 / 851 / 3133 | 1.0 / 1.0 / 3.6 | Belong behind a gear/help icon. | storage-*, logs-*, glossary-* |
| Settings | Configuration | 1 | 1 | 14 | 59 (733 under "More") | 1.0; More 4.4 / 6.9 | 8 tabs; "More settings" is 4.4 screens. The ASTAP banner says "Set astap_path or SEESTACK_ASTAP_PATH" (an environment variable, to a non-technical owner). Below the nav fold. | settings-* |
| Compare / Show | Utility views | 1 / 0 | – | – | 25 / 45 | 1.0 | Not in the nav; reached from Gallery. Fine. | compare-*, show-* |

## 3. Journey friction, ranked (2x2 mosaic, 1440x900)
1. **Editing blind.** Open the editor: the picture is 185 px tall above the fold. Expand "Stretch": its sliders land about 650 px below the bottom of the image, so every drag is done without seeing the result. Phone is worse (image top −824 px when an op is open). This is the core of priority #1.
2. **Which button?** The target header has "Process target", "Re-run QC + Solve", "Stack" (both of the first and last are primary-coloured), "Edit", "History" and "Save / share". A beginner cannot tell "Process target" from "Stack".
3. **Stack form ends in prose, not a button.** Start stacking is below the fold, under expert toggles and two notices. After the stack finishes the page stays on the form, and the next step is a small "View result in History" link. Then History, then Edit: 3 hops from "done" to "my picture".
4. **Slow first paint where he lives.** Target page idle 8.8–18 s (41 API calls, best-months 7.2 s); editor 5.9–9.3 s; Dashboard 37 calls. All of this is on a 3-target library, so at 100 targets it will be worse.
5. **Export choice overload.** Four outputs (new image, full PNG, share JPEG, print file) plus caption, print size and a Drizzle lecture. The owner wants "download my picture".
6. **Advice he can't act on in the moment.** "It's bigger than this mosaic … 18 h", "How's my stack? … darks would tidy hot pixels", "Use Luminance background flatten" (with the claim that the default makes cyan cores) all appear on the editing and stacking path.
7. **Phone:** Dashboard is 4.9 screens; with the menu open, 4 of 19 nav links are below the fold.

## 4. Proposed IA (nothing removed)
Actual tree today: 19 sidebar links, grouped as
- (lead) Dashboard
- Your pictures: Library, Gallery, My best pictures, Your sky so far (+ /sky-so-far/:year), My life list, Your universe
- Plan a night: Tonight, Sky Map
- Capture & process: Tonight live, Telescope, Moon & Sun, Calibration, Channel combine
- System: Jobs, Storage, Logs, Glossary, Settings

Off-nav routes: /show, /compare, /targets/:safe, /targets/:safe/stack, /targets/:safe/history, /targets/:safe/edit/:runId, /settings/:section. That is 27 routes.

Proposed: **4 top-level destinations plus header icons**
- **Home** (Dashboard): one notice board, then "your newest picture" with a single next step, then this week's totals.
- **Pictures** (`/library`), with tabs: Targets · Gallery · Best · My sky (Sky so far, Year, Life list, Universe as sub-tabs). Show and Compare stay where they are reached from.
  - **Target** `/targets/:t` = Picture (hero image + Edit + Download) · Frames (QC table, reject, Auto-grade) · Stacks (History, New stack) · Plan (best months, next session, mosaic coverage) · Notes
  - **Editor**: image left and sticky; tabs on the right: Adjust · About this picture (object card, framing, How's my stack) · Export
- **Plan** (`/tonight`), with tabs: Tonight · Sky Map · Live (Tonight, live)
- **Tools**: Telescope · Calibration · Moon & Sun · Channel combine
- Header: Scan · Jobs badge (opens Jobs) · ? (Glossary) · gear (Settings, Storage, Logs)

Every current page stays within 2 clicks. The sidebar drops from 19 links to 4 plus 3 icons.

## 5. Biggest UX improvements (ranked)
1. **Editor: picture first, always in view.** Make the preview `position: sticky` in a two-column layout. Fold the object card, framing and "How's my stack?" into one "About this picture" tab or collapsed row. On phone, pin a preview strip while an op is open. Evidence: image top y=715/900; slider ≈1850 vs image bottom ≈1200; phone img top −824. **M. NEW** (no "sticky" or editor-fold entry in IMPROVEMENTS.md).
2. **Target page: one hero, one primary action, nested tabs.** Picture + "Edit" (primary) + "Stack again" + a "More" menu (QC re-run, History, Save/share). Move the per-sub table and reject controls into a Frames tab, and the planning notices into a Plan tab. Lazy-load the plan endpoints so best-months no longer costs 7.2 s on open. Evidence: 6 buttons, 2 notices above the title, 41 requests, 8.8–18 s. **M. Partly FILED** (v0.507.6 slice 1 moved tabs; the header and frames table were never addressed).
3. **Nav: 19 links → 4 plus icons** (section 4). Evidence: Settings at y=936 and Glossary at 895 on a 900-px screen; 6 "pictures" variants; Channel combine and Moon & Sun at top level. **S–M. NEW** as a concrete tree (v0.437.0 set the IA priority but never touched the nav).
4. **Stack form: just "Start".** Show the output name, a one-line summary and Start above the fold. Sigma κ, Min/max, Mono and Drizzle outlier go under Advanced. Pick background mode per target automatically ("Auto" chooses luminance when the app already measured it should) instead of a 100-word paragraph. After the stack finishes, offer "Open in editor" directly. **S. Partly FILED** (line ~2075 "reduce visible option clutter (progressive disclosure)"). The automatic mode is NEW and needs care under §9 defaults.
5. **One notice board per page, capped at two lines each.** Every notice gets a one-sentence headline plus "Why?". Dashboard incoming-lag note: 90 words → 1 line. Fix the contradictions: the ASTAP banner calling solving "required" above finished stacks, and "Famous, easy" over CHALLENGING targets. **S. NEW.**
6. **Measure clutter on the rendered page, not the route file** (section 6). **S. NEW.**
7. **Merge the "your pictures" family into Pictures tabs.** Totals currently appear 3 times (Dashboard tiles, Sky so far, Life list) and the picture strip 3 times (Dashboard, Gallery, Best). **M. NEW.**
8. **Export: one "Download my picture" button**, with TIFF/FITS, share JPEG and print behind "More formats". The Drizzle print lecture becomes a tooltip. **S. NEW.**

## 6. Does the clutter ratchet measure the right thing?
No. `tests/test_ui_clutter_budget.py` regex-counts `<…Card|Note|…>` names and `<Alert` in the route file only. The declutter slices v0.507.6–.12 mostly moved surfaces into `components/` or wrapped them in `AlertNoticeBoard` / `alertNoticeNode`, so the counts fell and the pixels did not. Transitive import closure (my script `audit/ux/closure.py`, run from `frontend/src`):

| Route | Route-only (kinds, Alerts) | Closure (kinds, Alerts, alertNoticeNode) |
|---|---|---|
| Dashboard | 0, 0 | 24, 16, 0 |
| Target | 17, 0 | 32, 23, 14 |
| Editor | 6, 2 | 6, 10, 3 |
| Stack | 2, 5 | 2, 12, 3 |
| Jobs | 2, 0 | 2, 6, 3 |

The rendered Dashboard still shows ~9 top-level blocks; the rule allows 5.

**Better measure:** use what the dogfood probe already computes, on the rendered page at 1440x900 with mosaic data. Ratchet per route:
- (a) visible top-level blocks in `<main>` (≤5)
- (b) notices visible above the fold (≤2)
- (c) words above the fold
- (d) the y of the page's primary object (editor image, target picture, Start button) — must be < 50% of the viewport
- (e) page height in screens

Run it in CI as a Playwright check over the dogfood fixture, and keep the source regex only as a cheap pre-check.

## 7. Bugs hit
| # | Severity | Repro | Confidence |
|---|---|---|---|
| 1 | 🟠 UX | Editor preview not visible while editing. 1440x900 → `/targets/<mosaic>/edit/<run>` → click "Stretch" → slider at ≈y 1850, image spans ≈760–1200. Phone 390x844: img top −824. | High (measured) |
| 2 | 🟡 | Settings and Glossary nav links below the fold at 1440x900 (y=936/895). The sidebar is an inner ScrollArea with no scroll affordance. Visible without scrolling at 1920x1080; clipped at any window ≤ ~950 px high (most laptops). | High |
| 3 | 🟡 | Stack form's Start stacking button below the fold at 1440x900 (y=1209) on the mosaic target. | High |
| 4 | 🟡 perf | Target page idle 8.8–18 s on a 21-sub demo. `/api/plan/best-months/<t>` 7.2 s, `/api/plan/next-session` 3.7 s, both fetched on open for content inside a non-default tab. | High (timed twice) |
| 5 | ⚪ | Done jobs show the raw stage string "stack:Saving 1/1" (`seestack/stack/stacker.py` `progress("Saving",1,1)` surfaced verbatim by Jobs). | High |
| 6 | ⚪ copy | Dashboard "Try something new tonight" says "Famous, easy targets" but lists IC 1805 CHALLENGING / NEEDS 5x7 MOSAIC first (`components/SuggestTargetsCard.tsx:98`). | High |
| 7 | ⚪ copy | The ASTAP-missing banner says solving is "required before you can stack anything" while 3 sample stacks exist. The Settings banner tells a non-technical owner to set `SEESTACK_ASTAP_PATH`. | High |
| 8 | ⚪ trust | Target mosaic page: "Is it enough yet? 4 min of ~7 h" beside "9 panels … about 18 h". Two goals on one screen with no link between them. | Medium |
| 9 | ⚪ | "My best pictures" ranks the 6-frame, 1-min single field #1 above two 21-frame mosaics under "deepest, cleanest first". | Low–medium (may be the cleanest-metric design) |
| 10 | ⚪ | Journey step "Save / share" button not found by role on the mosaic target after a fresh load (30 s timeout), though it is in the screenshot. Possibly a slow render or a role-name mismatch. | Low |

No console errors or page errors on any of the 56 page loads.
