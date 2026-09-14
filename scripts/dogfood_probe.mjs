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
// Two views it reaches that a route table cannot. `/compare` is the only page
// whose URL carries data — two `<safe>:<run_id>` refs — so it was never in the
// table at all, and the page whose entire job is weighing two pictures against
// each other had never been in front of a browser; the route is now built from
// the app's own /api/gallery. And its Split and Blink comparators are behind a
// SegmentedControl, carrying a provenance strip "Side by side" does not have —
// so navigating could not see them, which is where v0.440.0 lived. Each mode is
// clicked and held to the identical checks.
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

/** The comparators that only exist behind a click. `page.goto` lands on "Side
 * by side", so a sweep that only navigates can never see the other two — the
 * same blind spot `--editor` exists for on the editor. */
const COMPARE_MODES = ["Split", "Blink"];

// The real route table (frontend/src/main.tsx) — a typo here reads as a bug
// ("Unexpected Application Error! 404 Not Found") that is entirely the probe's.
const ROUTES = [
  "/", "/library", "/gallery", "/best", "/sky-so-far", "/tonight", "/sky",
  "/universe", "/life-list",
  "/telescope", "/moon-sun", "/calibration", "/combine", "/jobs", "/storage",
  "/logs", "/settings", "/glossary",
  ...(COMPARE ? [COMPARE] : []),
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

const browser = await chromium.launch(
  BUNDLED ? { executablePath: BUNDLED } : {},
);
let findings = 0;
/** [width name, route, full-page scroll height] — reported at the end. */
const heights = [];
/** What the Target page prescribes, collected once (desktop) and printed at the
 *  end so the sentences land together rather than scattered through the sweep. */
let claims = [];
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
    // click below, so a route's height is always its *landing* height.
    heights.push([name, route, (await page.evaluate(
      () => document.documentElement.scrollHeight))]);
    // Compare's other two comparators are behind a SegmentedControl, and they
    // carry a provenance strip that "Side by side" does not — a whole element
    // this sweep could not reach by navigating. One click each, then the same
    // checks. A missing control is not a finding: the page legitimately refuses
    // Split when a stack has no preview.
    if (COMPARE && route === COMPARE) {
      for (const mode of COMPARE_MODES) {
        errors.length = 0;
        const button = page.getByText(mode, { exact: true }).first();
        if (!(await button.count())) continue;
        await button.click();
        await page.waitForTimeout(600);
        await probeCurrentView(`${route} [${mode}]`, `${slug}_${mode.toLowerCase()}`);
      }
    }
    // Collected at the desktop width only: the phone pass would say the same
    // sentences twice, and the fold is decided by priority rather than by width.
    if (SAFE && route === `/targets/${SAFE}` && name === "desktop") {
      claims = await page.evaluate(prescriptiveClaims, PRESCRIPTIVE);
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

// Tallest first, so the worst offender is the first line you read.
console.log("\npage height (full-page scroll height, tallest first):");
for (const [name, route, h] of heights.sort((a, b) => b[2] - a[2]).slice(0, 8)) {
  console.log(`  [${name}] ${route}: ${h}px`);
}
console.log(findings ? `${findings} thing(s) to look at` : "nothing overflowing, no console errors");
