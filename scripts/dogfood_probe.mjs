// Drive a real browser over a running AstroStack and report what looks wrong.
//
// Run through scripts/agent-dogfood.sh, which boots the app with sample data and
// installs playwright into a scratch dir first. Two things happen per page:
//
//   * a full-page screenshot at 1440 px and at 420 px (the owner reads this app
//     on a phone, and half the layout bugs only exist at one of those widths);
//   * an OVERFLOW PROBE — every leaf element whose scrollWidth exceeds its
//     clientWidth, minus the ones that opted into truncation with
//     text-overflow: ellipsis. That is the check that caught the Gallery's
//     primary button rendering as "Edit imag" (v0.263.4);
//   * a SQUEEZE PROBE — text shrunk *below* its own words without overflowing,
//     which is the ribbon the overflow probe is blind to by construction (the
//     Dashboard sample card, v0.264.4, was found by eye instead);
//   * a CLIPPED-LABEL PROBE — a badge/chip narrower than the one word it exists
//     to say. This is the overflow probe's own blind spot, and it is worth its
//     own pass because the exclusion that creates it is right in general and
//     wrong here: `text-overflow: ellipsis` reads as "the author chose to
//     truncate", but Mantine's `Badge` ships it as component style, so *every*
//     badge is silently exempt. That is how the Nights table's verdict went four
//     dogfood passes rendering as "SH…" at 420 px — ellipsised inside the badge,
//     where scrolling the table could never reveal it (v0.434.1).
//
// It also reports each page's full-page height, tallest first: the standing
// information-architecture work is scored on exactly that number, and it kept
// being measured by hand off these screenshots after the fact.
//
// And it prints the Target page's PRESCRIPTIVE CLAIMS — every card that tells
// the owner what to do next — collected off the rendered page into one block,
// with whether each is inline or folded behind "N more notes". Those cards are
// computed in the frontend, so no server-side block can print them; four of the
// last five dogfood findings were two of those sentences disagreeing, and every
// one had to be found by cropping a screenshot afterwards.
//
// It prints the SAME block for the DASHBOARD'S NOTICE BOARD, which is the screen
// the owner actually opens and the one surface of twelve conditional notes that
// nothing had ever photographed as a paragraph. v0.444.3 came out of reading
// that board's *source* note by note — `StuckImportNote` stating a measured wait
// while `IncomingLagNote` guessed at the same cause an inch below and offered
// the opposite action — a finding this probe was structurally unable to make:
// every one of those notes is self-hiding on a healthy install, so a default
// pass sees an empty board, and even a `--incoming-lag` pass only printed what
// the *API* answered, never what the board said. Read off the board's own DOM
// rather than a list of test ids, so a note added tomorrow is in the block
// without anyone remembering to add it (and the two notes that are inline
// `<Alert>`s with no test id of their own are not silently skipped).
//
// Two views it reaches that a route table cannot. `/compare` is the only page
// whose URL carries data — two `<safe>:<run_id>` refs — so it was never in the
// table at all, and the page whose entire job is weighing two pictures against
// each other had never been in front of a browser; the route is now built from
// the app's own /api/gallery. And its Split and Blink comparators are behind a
// SegmentedControl, carrying a provenance strip "Side by side" does not have —
// so navigating could not see them, which is where v0.440.0 lived. Each mode is
// clicked and held to the identical checks.
//
// The route table below is mirrored from frontend/src/main.tsx by hand, and a
// hand-mirrored list goes stale: /show, /live and /sky-so-far/:year were all
// registered routes that no pass had ever opened — "Tonight, live" being a NAV
// entry whose own docstring says it lives on a phone. That cannot come back:
// tests/test_dogfood_route_coverage.py fails when main.tsx registers a route
// this file does not reach.
//
// A third kind of view a route table cannot reach: a page that hides most of
// itself behind a tab. `/settings` is one registered route and SEVEN sections,
// six of which are mounted-but-hidden and therefore invisible to all three DOM
// probes below — so the app's tallest-by-content page had been photographed as
// its first tab only, and Maintenance (updates, refinish, "Reprocess
// everything", Job history, Backup/restore, Access control) had never been drawn
// at all. Each section is now its own route; see SETTINGS_SECTIONS.
//
// It is a FINDER, not a test: what it reports still needs a real regression test
// in the suite before anything is called fixed.
import { existsSync } from "node:fs";
import { chromium } from "playwright";

// This container ships the browsers at $PLAYWRIGHT_BROWSERS_PATH and forbids
// `playwright install`, but the npm package we pull in may want a newer build
// than the one on disk. Launching the bundled binary by path sidesteps that;
// falling back to Playwright's own lookup keeps this working anywhere else.
const BUNDLED = [
  process.env.CHROMIUM_PATH,
  `${process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers"}/chromium`,
].find((p) => p && existsSync(p));

const BASE = process.env.BASE_URL || "http://127.0.0.1:8811";
const SHOTS = process.env.SHOTS_DIR || "/tmp/astrostack-dogfood/shots";
const SAFE = process.env.TARGET_SAFE || "";
const RUN_ID = process.env.TARGET_RUN_ID || "";

/** `/compare` needs two `<safe>:<run_id>` refs in its query string, so unlike
 * every other route it cannot be a constant — which is why it has never been in
 * this table, and why the A/B provenance strip above Split and Blink had never
 * been in front of a browser at all (v0.440.0 was a bug that lived exactly
 * there: the strip printed a raw frame count where the Side-by-side card on the
 * same page ran it through `field_fulls`).
 *
 * Built from the app's own `/api/gallery` rather than from an env var: the two
 * pictures a run has are already on the wire, no new plumbing is needed, and on
 * a `--mosaic` pass the pair is the mosaic *and* the single field — the one
 * comparison where a per-pixel figure and a total are different numbers.
 * Returns "" when there are fewer than two pictures (`--empty`, `--no-stack`),
 * and the route is then simply skipped rather than probing an error state the
 * page is right to show. */
async function compareRoute() {
  try {
    const res = await fetch(`${BASE}/api/gallery`);
    if (!res.ok) return "";
    const items = (await res.json()).items ?? [];
    if (items.length < 2) return "";
    const [a, b] = items;
    return `/compare?a=${a.safe}:${a.run_id}&b=${b.safe}:${b.run_id}`;
  } catch {
    return "";
  }
}

const COMPARE = await compareRoute();

/** The year drill-down, `/sky-so-far/:year`. Like `/compare` it cannot be a
 * constant — the year is a property of the library, not of the app — which is
 * why it was never in the table below and why "Your year under the stars" had
 * never been photographed at any width.
 *
 * Asked the same way the entry card asks (`YourYearCard` → `/api/recap/year/…`)
 * and resolved by the same rule as `yourYear.defaultRecapYear`: the most recent
 * year that actually has nights, because that is the year the card links to.
 * Returns "" when the library has no nights at all (`--empty`), where the card
 * self-hides and there is no route to sweep. */
async function yearRoute() {
  try {
    const thisYear = new Date().getUTCFullYear();
    const res = await fetch(`${BASE}/api/recap/year/${thisYear}`);
    if (!res.ok) return "";
    const years = ((await res.json()).years_with_data ?? [])
      .filter((y) => Number.isFinite(y));
    if (!years.length) return "";
    return `/sky-so-far/${Math.max(...years)}`;
  } catch {
    return "";
  }
}

const YEAR = await yearRoute();

/** Routes a pass has actually observed a view switch on.
 *
 * The switches themselves are discovered off the page (see `viewSwitches`
 * below) rather than listed, so a control added tomorrow is swept without
 * anyone remembering. What a list is still good for is the failure this
 * arrangement newly has: discovery keys off Mantine's own class names, so a
 * Mantine rename would find **nothing**, everywhere, and a sweep that silently
 * covers less than it did reports CLEAN exactly as before. Naming the routes
 * where a switch is known to exist turns that silence into a printed finding.
 *
 * `tests/test_dogfood_view_switches.py` pins each of these against the route
 * component that renders it, so a control genuinely removed is a red test
 * rather than a warning nobody reads. Gallery's and History's switches are
 * deliberately absent: they render only inside a modal / on data this sweep's
 * library does not have, so "no switch here" is the honest landing state. */
const KNOWN_VIEW_SWITCHES = ["/compare", "/logs", "/life-list", "/tonight", "/sky"];

/** The Settings page's own sections — the same blind spot again, and the one it
 * hid the most behind.
 *
 * `/settings` lands on the FIRST section (`SectionTabs` falls back to
 * `sections[0]`, i.e. Folders). The other six panels are in the DOM —
 * `keepMounted`, because the sections share one edit buffer — but Mantine hides
 * an inactive `Tabs.Panel`, so every element in them has a zero-size bounding
 * rect, which `overflowingLeaves`, `squeezedText` and `clippedLabels` all skip
 * by construction. So a `/settings` shot is a shot of Folders, and six sections
 * of the app's tallest-by-content page had never been drawn at any width, never
 * measured for overflow or squeezed text, and never watched for a console error.
 * Maintenance alone holds the updates card (v0.490.0), the refinish card
 * (v0.479.3), "Reprocess everything" with its three-way scope (v0.492.0), Job
 * history, Backup/restore and Access control.
 *
 * Mirrored by hand from `SETTINGS_SECTIONS` in
 * `frontend/src/settingsSections.ts`, and a hand-mirrored list goes stale — so
 * `tests/test_dogfood_route_coverage.py` reads that constant and goes red when a
 * section is missing here. Deliberately the WHOLE list rather than the six
 * `/settings` does not show: the point is that it is the app's own list, so a
 * renamed or added section cannot be silently skipped, and the cost of keeping
 * `folders` in it is two screenshots of a page we already have. */
const SETTINGS_SECTIONS = [
  "folders", "automation", "plate-solving", "observing-site", "stacking",
  "telescope", "maintenance",
];

// The real route table (frontend/src/main.tsx) — a typo here reads as a bug
// ("Unexpected Application Error! 404 Not Found") that is entirely the probe's.
const ROUTES = [
  "/", "/library", "/gallery", "/best", "/show", "/sky-so-far", "/tonight",
  // "Tonight, live" is the one NAV entry this table was missing, and its own
  // docstring says it is meant to be left open on a phone for hours — i.e. the
  // 420 px pass is the pass that matters for it, and it had never had one.
  "/live",
  "/sky", "/universe", "/life-list",
  "/telescope", "/moon-sun", "/calibration", "/combine", "/jobs", "/storage",
  "/logs",
  // `/settings` is where a URL typed by hand lands; the seven `/settings/<section>`
  // routes are the page's real content (see SETTINGS_SECTIONS above).
  "/settings", ...SETTINGS_SECTIONS.map((s) => `/settings/${s}`),
  "/glossary",
  ...(COMPARE ? [COMPARE] : []),
  ...(YEAR ? [YEAR] : []),
  ...(SAFE ? [`/targets/${SAFE}`, `/targets/${SAFE}/stack`,
              `/targets/${SAFE}/history`] : []),
  // The editor is priority 1, so it is worth a shot even though it is slow.
  ...(SAFE && RUN_ID ? [`/targets/${SAFE}/edit/${RUN_ID}`] : []),
];

const WIDTHS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "phone", width: 420, height: 860 },
];

// Both probes below run inside the page. They are passed to page.evaluate as
// functions (a *string* would be evaluated as an expression and hand back the
// function itself), so neither may close over module scope, and `evaluate`
// takes exactly one argument — hence the options object on `squeezedText`.

/** Text squeezed *below* its own words without overflowing — the failure mode
 * the overflow probe is blind to by construction. A `flexShrink`-0 neighbour in
 * a `nowrap` row can shrink a paragraph to ~50 px, at which point it wraps
 * obediently into a one-word-per-line ribbon; nothing overflows, so
 * `overflowingLeaves` reports nothing. That is exactly how the Dashboard's
 * sample card rendered ~25 lines tall on a phone (fixed v0.264.4), and it was
 * found by eye rather than by this harness. Flags a text block whose own box is
 * narrow while the row it sits in is comfortably wide — the signature of a
 * squeeze rather than of a genuinely narrow screen. */
function squeezedText({ minChars, minRatio }) {
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    if (el.children.length) continue;                 // leaves only
    const text = (el.textContent || "").trim();
    if (text.length < minChars) continue;             // a badge is meant to be small
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;              // hidden
    const parent = el.parentElement?.parentElement;
    if (!parent) continue;
    const pw = parent.getBoundingClientRect().width;
    if (!pw || r.width / pw > minRatio) continue;
    // Wrapping to two or three lines is normal; a ribbon is not. Approximate the
    // line count from the box's own height against its line-height.
    const lh = parseFloat(getComputedStyle(el).lineHeight) || 16;
    const lines = Math.round(r.height / lh);
    if (lines < 6) continue;
    out.push({
      tag: el.tagName.toLowerCase(), text: text.slice(0, 60),
      width: Math.round(r.width), parentWidth: Math.round(pw), lines,
    });
  }
  return out;
}

/** Leaf elements whose content is wider than the box drawn for it. */
function overflowingLeaves() {
  // Exclusions, each earned by a false positive on a real page: a text input
  // scrolls its own value by design (Settings), a scrollbar thumb is *meant* to
  // be narrower than its track (Logs), and anything inside a scroll container
  // is being scrolled deliberately.
  const SKIP_TAGS = new Set(["input", "textarea", "select", "svg", "path"]);
  const out = [];
  for (const el of document.querySelectorAll("body *")) {
    if (el.children.length) continue;                 // leaves only
    if (SKIP_TAGS.has(el.tagName.toLowerCase())) continue;
    if (el.closest("[data-scrollable], .mantine-ScrollArea-root")) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;              // hidden
    const s = getComputedStyle(el);
    if (s.textOverflow === "ellipsis") continue;      // deliberate truncation
    if (s.overflowX === "auto" || s.overflowX === "scroll") continue;
    if (el.scrollWidth - el.clientWidth > 1) {
      out.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.className || "").toString().slice(0, 60),
        text: (el.textContent || "").trim().slice(0, 60),
        clientWidth: el.clientWidth, scrollWidth: el.scrollWidth,
      });
    }
  }
  return out;
}

/** Badges and chips rendered narrower than the single word they carry.
 *
 * A `Badge` is a label, not prose: there is no "read the rest elsewhere" for it,
 * so an ellipsis inside one is never the deliberate truncation the overflow
 * probe's `text-overflow` exclusion assumes. And because the clip is *inside*
 * the badge, it survives any amount of scrolling — unlike a table that is merely
 * too wide, which a swipe fixes.
 *
 * Deliberately narrow: only badge-shaped anchors, and only when the label really
 * does not fit. Measured across 23 routes at 420 px on the sample library, that
 * was exactly one hit before the fix and none after, so it is a signal rather
 * than a wall of noise. The cure is `min-width: max-content` on the badge — let
 * the container grow (and scroll) rather than eat the word. */
function clippedLabels() {
  const out = [];
  for (const el of document.querySelectorAll(
    '[class*="mantine-Badge-root"], [class*="mantine-Chip-"]')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;              // hidden
    // The badge itself clips, or its inner label does.
    const parts = [el, ...el.querySelectorAll("*")];
    for (const p of parts) {
      const s = getComputedStyle(p);
      if (s.overflowX !== "hidden" && s.overflowX !== "clip") continue;
      if (p.scrollWidth - p.clientWidth <= 1) continue;
      out.push({
        text: (el.textContent || "").trim().slice(0, 40),
        clientWidth: p.clientWidth, scrollWidth: p.scrollWidth,
      });
      break;
    }
  }
  return out;
}

/** The views a page keeps behind a click, and the labels that reach them.
 *
 * Two shapes, both of which hide content from a sweep that only navigates:
 *
 * * a **SegmentedControl** swaps the rendered view outright — `/life-list`'s
 *   "Still to shoot", `/tonight`'s object-type filters, `/logs`' severities,
 *   `/sky`'s three maps, `/compare`'s Split and Blink;
 * * a collapsed **Accordion** panel is not in the layout at all — the Stack
 *   form's "Advanced options" is every advanced stacking control in the app.
 *
 * Read off the page's own DOM rather than listed here, for the reason the route
 * table's comment gives about hand-mirrored lists: a filter added tomorrow is
 * swept without anyone remembering, and `COMPARE_MODES` — which is what this
 * replaces — had been a two-string list covering one page since v0.440.2.
 *
 * Every option is returned, each marked `active` when it is the one already
 * showing — the caller seeds its own "done" set from that, so the landing view
 * is not re-probed after the loop has clicked past it and come back round.
 *
 * Deliberately only these two controls. Both are disclosure — they change what
 * is drawn and nothing else — so a sweep may click them freely, which is not
 * true of buttons in general. */
function viewSwitches() {
  const out = [];
  for (const el of document.querySelectorAll(
    '[class*="mantine-SegmentedControl-label"]')) {
    const text = (el.textContent || "").trim();
    if (!text) continue;
    // Active by either of the two marks Mantine leaves — `data-active` on the
    // label, and the radio it labels being checked.
    const input = el.control
      || document.getElementById(el.getAttribute("for") || "");
    const active = el.getAttribute("data-active") === "true"
      || Boolean(input && input.checked);
    out.push({ kind: "view", label: text, active });
  }
  for (const el of document.querySelectorAll(
    '[class*="mantine-Accordion-control"]')) {
    const text = (el.textContent || "").trim();
    if (!text) continue;
    out.push({
      kind: "panel", label: text,
      active: el.getAttribute("aria-expanded") === "true",
    });
  }
  return out;
}

/** Open every shut disclosure panel on the page, in one round trip.
 *
 * Driven in-page rather than through Playwright's actionability machinery, and
 * that is a deliberate difference from the view switches above: the Glossary
 * carries **forty** terms, and forty `locator.click()`s with a fresh discovery
 * between each cost more than every other route in the sweep put together. A
 * disclosure control has nothing to simulate — it toggles a panel and does
 * nothing else — so the page's own `click()` reaches the same state, and what
 * is then probed is identical.
 *
 * Loops a few times because opening a panel can reveal a nested one; stops as
 * soon as a pass opens nothing. Returns how many it opened, for the label. */
function expandAllPanels() {
  let opened = 0;
  for (let round = 0; round < 4; round += 1) {
    const shut = Array.from(document.querySelectorAll(
      '[class*="mantine-Accordion-control"]'))
      .filter((el) => el.getAttribute("aria-expanded") !== "true");
    if (!shut.length) break;
    for (const el of shut) { el.click(); opened += 1; }
  }
  return opened;
}

/** Every sentence on the Target page that tells the owner what to DO next,
 *  collected off one rendered page so they can be read as one paragraph.
 *
 *  Why by `data-testid` and not by looking at the API: these are computed in the
 *  frontend (`readiness.ts`, `nextBestMove.ts`, `integrationTrend.ts`,
 *  `grainProjection.ts`), so nothing server-side can print them — which is
 *  exactly why `agent-dogfood.sh`'s "what the app SAYS about this mosaic" block
 *  has only ever carried the two cards that *are* server-side (the panel map and
 *  the health notes). Four of the last five dogfood findings were two of these
 *  sentences disagreeing rather than one of them being wrong, and every one of
 *  them had to be found by cropping a screenshot afterwards.
 *
 *  The `folded` flag is the other half, and it is the reason this reads the DOM
 *  rather than the props: `NoticeBoard` keeps every note **mounted and hidden
 *  with CSS**, showing the two highest-priority speakers inline and folding the
 *  rest behind "N more notes". So "what does the page say?" and "what does the
 *  reader see without clicking?" are different questions, and the second one is
 *  the one the 2026-09-13 process note asks ("check what the page says when the
 *  other cards are quiet"). A zero-height box is folded; anything with a box is
 *  inline. */
const PRESCRIPTIVE = [
  "thin-stack-warning", "next-best-move", "integration-trend",
  "readiness-card", "mosaic-map-card", "stack-health-card",
  "over-trimmed-target-note", "rejection-outlook-note", "framing-verdict",
];

/** The same question, on `/tonight` — the other page that *prescribes*.
 *
 *  The Target page tells the owner what to do with a picture he already has;
 *  this one tells him where to point tonight, and it does so from **four
 *  independent self-hiding cards** stacked in a column, each of which names a
 *  target and none of which knows what the others said. That is the shape every
 *  finding of the last six runs has had, and until v0.445.0 nobody had read this
 *  column as one paragraph: `ClosingSeasonCard` argued "a clear night spent on
 *  one of these buys something the rest of the year can't" while `PlanWeekCard`,
 *  an inch below, answered "which night should I go out?" from a score that has
 *  never heard of a season ending.
 *
 *  Listed by test id rather than walked structurally, unlike `noticeBoardClaims`:
 *  these are siblings in a plain `<Stack>` alongside the page's own header, the
 *  two big tables and the three summary cards, so there is no container whose
 *  children *are* the claims. Every one of them carries a test id today; a new
 *  card that does not will be missed, which is the cost of the page not having a
 *  board. It is also why this list, unlike `PRESCRIPTIVE`, is worth re-reading
 *  against `routes/Tonight.tsx` when a card is added.
 *
 *  Note `/tonight` is empty of all four without an observing site — which every
 *  pass before v0.436.1 was. A normal pass now sets one. */
const TONIGHT_PRESCRIPTIVE = [
  "wishlist-tonight-card", "nearly-there-card", "closing-season",
  "plan-week", "plan-week-closing", "worth-more-time",
];

function prescriptiveClaims(ids) {
  // `innerText` is what a reader gets — but it is empty on a `display: none`
  // note, which is precisely the folded case worth reporting. So fall back to
  // walking the leaves, which gives the same words with explicit separators
  // instead of `textContent`'s run-together mush.
  function claimText(el) {
    const visible = el.getBoundingClientRect().height > 0;
    if (visible) return (el.innerText || "").trim().replace(/\s*\n+\s*/g, " · ");
    const parts = [];
    for (const n of el.querySelectorAll("*")) {
      if (n.children.length) continue;
      const t = (n.textContent || "").trim();
      if (t) parts.push(t);
    }
    return parts.join(" · ");
  }
  const out = [];
  for (const id of ids) {
    for (const el of document.querySelectorAll(`[data-testid="${id}"]`)) {
      const text = claimText(el);
      if (!text) continue;
      out.push({
        id,
        folded: el.getBoundingClientRect().height === 0,
        text: text.slice(0, 400),
      });
    }
  }
  return out;
}

/** What a `NoticeBoard` is saying, in its own display order.
 *
 *  The board's children ARE the notes: `NoticeBoard` sorts by priority, renders
 *  one wrapper `<div>` per item, and hides the ones past `inlineCount` with
 *  `display: none` rather than unmounting them. So walking those wrappers gives
 *  every note the board holds, in the order a reader meets them, with the fold
 *  readable off the box height — the same rule `prescriptiveClaims` uses.
 *
 *  Read structurally instead of from a list of test ids on purpose. A list would
 *  need editing every time a note is added (twelve exist today, and two of them
 *  — the folder and ASTAP readiness alerts — are inline `<Alert>`s with no test
 *  id at all, so a list would have quietly omitted them). The label falls back
 *  to the wrapper's own test id when its note carries one, which is most of them.
 *
 *  Deliberately a near-duplicate of `prescriptiveClaims`' text extraction rather
 *  than a shared helper: both are serialised into the page by `page.evaluate`,
 *  which cannot close over anything defined out here. */
function noticeBoardClaims(testId) {
  const board = document.querySelector(`[data-testid="${testId}"]`);
  if (!board) return [];
  const out = [];
  for (const host of board.children) {
    // The "N more notes" discloser is the board's own child, not a note.
    if (!host.matches("div")) continue;
    const hidden = host.getBoundingClientRect().height === 0;
    let text;
    if (!hidden) {
      text = (host.innerText || "").trim().replace(/\s*\n+\s*/g, " · ");
    } else {
      // `innerText` is empty on a `display: none` subtree, which is exactly the
      // folded case worth reporting — so walk the leaves instead.
      const parts = [];
      for (const n of host.querySelectorAll("*")) {
        if (n.children.length) continue;
        const t = (n.textContent || "").trim();
        if (t) parts.push(t);
      }
      text = parts.join(" · ");
    }
    if (!text) continue;               // a note that is silent, i.e. most of them
    const tagged = host.querySelector("[data-testid]");
    out.push({
      id: tagged ? tagged.getAttribute("data-testid") : "(untagged alert)",
      folded: hidden,
      text: text.slice(0, 400),
    });
  }
  return out;
}

const browser = await chromium.launch(
  BUNDLED ? { executablePath: BUNDLED } : {},
);
let findings = 0;
/** [width name, route, full-page scroll height] — reported at the end. */
const heights = [];
/** What the Target page prescribes, collected once (desktop) and printed at the
 *  end so the sentences land together rather than scattered through the sweep. */
let claims = [];
/** What the Dashboard's notice board says, same treatment, collected on `/`. */
let notices = [];
/** What the Tonight page's four prescribing cards say, collected on `/tonight`. */
let tonight = [];
for (const { name, width, height } of WIDTHS) {
  const ctx = await browser.newContext({ viewport: { width, height } });
  const page = await ctx.newPage();
  const errors = [];
  // A container with no outbound network makes the Sky Map's remote sky survey
  // fail loudly; that says nothing about this app, so it isn't a finding.
  //
  // Two of Aladin's complaints name no URL, so the test above cannot tell they are
  // about a remote tile: a bare "TypeError: Failed to fetch", and "Image HDU not
  // found in the FITS" (Aladin parsing a tile it never really received). Both were
  // reported as findings on /sky by the 2026-08-17 run against a build where
  // nothing was wrong. They are excused **only on the Sky Map route**, on purpose:
  // "Failed to fetch" anywhere else means one of *our* API calls died, which is a
  // real finding and must keep surfacing.
  const ALADIN_NOISE = /^TypeError: Failed to fetch$|Image HDU not found in the FITS/;
  let currentRoute = "";
  const ours = (t) => !/https?:\/\/(?!127\.0\.0\.1|localhost)/.test(t)
    && !/ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED|HiPS/.test(t)
    && !(currentRoute === "/sky" && ALADIN_NOISE.test(t.trim()));
  page.on("pageerror", (e) => { if (ours(String(e))) errors.push(String(e)); });
  page.on("console", (m) => {
    if (m.type() === "error" && ours(m.text())) errors.push(m.text());
  });

  /** Shoot and measure whatever the page is showing right now.
   *
   * Split out of the route loop so a view reached by a *click* — a comparator
   * mode, and anything else added later — is held to the identical checks as a
   * view reached by a URL. `label` is what the findings are reported under;
   * `slug` names the screenshot. */
  const probeCurrentView = async (label, slug) => {
    await page.screenshot({
      path: `${SHOTS}/${name}${slug}.png`, fullPage: true,
    });
    for (const o of await page.evaluate(overflowingLeaves)) {
      findings++;
      console.log(
        `[${name}] ${label}: OVERFLOW <${o.tag}> ${o.clientWidth}px box vs ` +
        `${o.scrollWidth}px content — "${o.text}" (${o.cls})`,
      );
    }
    for (const s of await page.evaluate(squeezedText, { minChars: 40, minRatio: 0.35 })) {
      findings++;
      console.log(
        `[${name}] ${label}: SQUEEZED <${s.tag}> ${s.width}px of a ${s.parentWidth}px ` +
        `row, ${s.lines} lines — "${s.text}"`,
      );
    }
    for (const c of await page.evaluate(clippedLabels)) {
      findings++;
      console.log(
        `[${name}] ${label}: CLIPPED LABEL ${c.clientWidth}px box vs ` +
        `${c.scrollWidth}px word — "${c.text}" (scrolling cannot reveal it)`,
      );
    }
    for (const e of errors.slice(0, 3)) {
      findings++;
      console.log(`[${name}] ${label}: CONSOLE ERROR ${e.slice(0, 200)}`);
    }
  };

  for (const route of ROUTES) {
    errors.length = 0;
    currentRoute = route;   // the console/pageerror handlers filter by route
    try {
      await page.goto(BASE + route, { waitUntil: "networkidle", timeout: 20000 });
    } catch {
      // The Sky Map keeps talking to a remote survey, so it never goes idle —
      // shoot and probe it anyway rather than skipping the page entirely.
      console.log(`[${name}] ${route}: never went network-idle; probing anyway`);
    }
    await page.waitForTimeout(400);   // let self-hiding cards make their minds up
    const slug = route.replace(/\W+/g, "_") || "root";
    await probeCurrentView(route, slug);
    // How far the owner has to scroll. Not a finding on its own — a settings
    // page is legitimately long — but the standing information-architecture
    // work (AGENTS.md §1) is scored on exactly this number, and it has twice
    // been measured by hand from these screenshots afterwards. Report it here
    // so "which page is the wall?" is answered by the run. Taken before any
    // click below, so a route's *landing* height is always recorded as the bare
    // route; a view reached by a click is recorded under its own label, because
    // the tallest thing this app draws is one of those (see below) and a table
    // that only knew landing heights answered "which page is the wall?" wrong
    // by a factor of four.
    heights.push([name, route, (await page.evaluate(
      () => document.documentElement.scrollHeight))]);
    // What the page keeps behind a click. `page.goto` lands on one view of a
    // SegmentedControl and on a shut Accordion, so everything else was
    // structurally unreachable: Compare's Split and Blink carry a provenance
    // strip "Side by side" does not (v0.440.0 lived exactly there), the Stack
    // form's "Advanced options" is every advanced stacking control in the app,
    // the Glossary's forty term bodies are forty blocks of prose, and
    // `/life-list`'s "Still to shoot" measured **14,492 px** on a phone — 4.3x
    // the tallest landing height any pass had ever recorded, one click from a
    // nav page, never drawn.
    //
    // The two shapes are swept differently on purpose:
    //
    // * a **view** switch replaces the page, so each one is its own probe and
    //   its own height row — those heights are what "which page is the wall?"
    //   is actually asking, and the landing-only table answered it wrong by a
    //   factor of four;
    // * a **panel** adds to the page it is on, so they are opened *together*
    //   (in one round trip, see `expandAllPanels`) and probed once. One at a
    //   time would mean forty screenshots of a growing Glossary, and forty
    //   cumulative heights that are nobody's page — the tallest of them would
    //   top the wall table while describing a state no reader is ever in. One
    //   "everything disclosed" probe catches an overflow in any panel at the
    //   cost of one shot, and pushes no height.
    //
    // Discovery is re-run after each click: a switch can reveal a switch, and a
    // click re-renders, so element handles do not survive. Clicking by label
    // keeps that honest. A control may legitimately refuse — Compare refuses
    // Split when a stack has no preview — which is the page's call, not a
    // finding.
    const clickByLabel = async (label) => {
      const control = page.getByText(label, { exact: true }).first();
      if (!(await control.count())) return false;
      return control.click({ timeout: 5000 }).then(() => true, () => false);
    };
    const switchesOf = async (kind) =>
      (await page.evaluate(viewSwitches)).filter((s) => s.kind === kind);

    // Seeded with the view the landing probe just shot, so clicking round the
    // control does not come back to it and photograph it a second time.
    const seenViews = new Set(
      (await switchesOf("view")).filter((s) => s.active).map((s) => s.label));
    const viewCount = (await switchesOf("view")).length;
    for (let round = 0; round < 16; round += 1) {
      const next = (await switchesOf("view"))
        .find((s) => !seenViews.has(s.label));
      if (!next) break;
      seenViews.add(next.label);
      errors.length = 0;
      if (!(await clickByLabel(next.label))) continue;
      await page.waitForTimeout(600);
      const viewSlug = next.label.replace(/\W+/g, "_").toLowerCase();
      await probeCurrentView(`${route} [${next.label}]`, `${slug}_${viewSlug}`);
      heights.push([name, `${route} [${next.label}]`, (await page.evaluate(
        () => document.documentElement.scrollHeight))]);
    }

    // Back to the landing view before disclosing, so "everything open" is a
    // state a reader can actually reach from the page as it arrives, rather
    // than whichever view the loop above happened to leave behind.
    const shutPanels = (await switchesOf("panel")).filter((s) => !s.active);
    if (shutPanels.length) {
      if (seenViews.size) {
        await page.goto(BASE + route, { waitUntil: "networkidle", timeout: 20000 })
          .catch(() => {});
        await page.waitForTimeout(400);
      }
      errors.length = 0;
      const opened = await page.evaluate(expandAllPanels);
      if (opened) {
        await page.waitForTimeout(500);
        await probeCurrentView(
          `${route} [${opened} panel${opened === 1 ? "" : "s"} open]`,
          `${slug}_panels`,
        );
      }
    }
    // Discovery keys off Mantine's own class names, so a Mantine rename finds
    // nothing everywhere and a sweep that covers less reports CLEAN exactly as
    // before. Say so where a switch is known to exist.
    // `/compare` carries two picture refs in its query string, so match the path.
    if (KNOWN_VIEW_SWITCHES.includes(route.split("?")[0]) && viewCount === 0) {
      findings++;
      console.log(
        `[${name}] ${route}: NO VIEW SWITCH FOUND, but this page has one — ` +
        `viewSwitches() found nothing to click (a Mantine class rename?). ` +
        `Everything behind it is unswept.`,
      );
    }
    // Collected at the desktop width only: the phone pass would say the same
    // sentences twice, and the fold is decided by priority rather than by width.
    if (SAFE && route === `/targets/${SAFE}` && name === "desktop") {
      claims = await page.evaluate(prescriptiveClaims, PRESCRIPTIVE);
    }
    // Same reasoning, and the same width: the fold is decided by priority, not
    // by how wide the window is.
    if (route === "/" && name === "desktop") {
      notices = await page.evaluate(noticeBoardClaims, "dashboard-notes");
    }
    // Same treatment, same width, same reason: these cards self-hide on data,
    // not on how wide the window is.
    if (route === "/tonight" && name === "desktop") {
      tonight = await page.evaluate(prescriptiveClaims, TONIGHT_PRESCRIPTIVE);
    }
  }
  await ctx.close();
}
await browser.close();

if (claims.length) {
  console.log(
    `\nwhat the Target page SAYS about ${SAFE} — read these as ONE paragraph and`
    + "\nask whether a beginner could hold all of them at once. Four of the last"
    + "\nfive findings were two of these disagreeing, not one of them wrong:");
  for (const c of claims) {
    const where = c.folded ? 'FOLDED behind "more notes"' : "inline";
    console.log(`   [${c.id}, ${where}] ${c.text}`);
  }
  const inline = claims.filter((c) => !c.folded).length;
  console.log(
    `   (${inline} of ${claims.length} are visible without a click — the folded`
    + " ones are what the page does NOT say to a reader who never expands it)");
}

if (notices.length) {
  console.log(
    "\nwhat the DASHBOARD'S notice board SAYS — the same question, on the screen"
    + "\nthe owner actually opens. Two notes stay inline; ask of the pair whether"
    + "\none is guessing at something the other has measured, whether they point"
    + "\nthe same way, and whether either says twice what the board only has room"
    + "\nto say once (that trio is exactly what v0.444.3 fixed):");
  for (const n of notices) {
    const where = n.folded ? 'FOLDED behind "more notes"' : "inline";
    console.log(`   [${n.id}, ${where}] ${n.text}`);
  }
  const inline = notices.filter((n) => !n.folded).length;
  console.log(
    `   (${inline} of ${notices.length} speaking notes are visible without a click)`);
} else {
  // Worth saying out loud: an empty board is the healthy answer, and it is also
  // what every pass before `--incoming-lag` existed could ever have seen. A
  // "CLEAN" here is a statement about a board with nothing on it.
  console.log(
    "\nthe Dashboard's notice board is silent (a healthy install — seed a fault"
    + " with --incoming-lag to read it)");
}

if (tonight.length) {
  console.log(
    "\nwhat the TONIGHT page SAYS — the other page that PRESCRIBES, and the one"
    + "\nwhere four self-hiding cards each name a target without knowing what the"
    + "\nothers named. Read them as ONE paragraph and ask: do they point at the"
    + "\nsame night and the same target, and if not, does the page say which wins?"
    + "\n(v0.445.0 was exactly that — 'shoot these before they're gone' against a"
    + "\nweek plan scored on altitude alone):");
  for (const c of tonight) {
    const where = c.folded ? "hidden" : "inline";
    console.log(`   [${c.id}, ${where}] ${c.text}`);
  }
} else {
  // Not a clean bill of health: without an observing site these cards cannot
  // speak at all, and that was every pass before v0.436.1.
  console.log(
    "\nthe Tonight page prescribes nothing (no observing site, or nothing of"
    + " yours is well placed — check the location_source line above)");
}

// Tallest first, so the worst offender is the first line you read.
console.log("\npage height (full-page scroll height, tallest first):");
for (const [name, route, h] of heights.sort((a, b) => b[2] - a[2]).slice(0, 8)) {
  console.log(`  [${name}] ${route}: ${h}px`);
}
console.log(findings ? `${findings} thing(s) to look at` : "nothing overflowing, no console errors");
