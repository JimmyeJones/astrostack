// Measure the frames table at the owner's SCALE, in a real browser.
//
// Every other drive in this directory asks what the app *says*. This one asks
// what it *costs*, because the defect it exists for was invisible to every
// question the tooling already knew how to ask:
//
//   * `dogfood_probe.mjs` measures **page height**, and the frames table lives
//     inside `<Table.ScrollContainer mah="65vh">`, whose height is by
//     construction independent of how many rows it holds. So a table rendering
//     one DOM row per sub — ~22 nodes each, ~121,000 nodes on the owner's
//     5,477-sub target and ~790,000 on his 35,894-sub one — measured exactly the
//     same as a table rendering six (v0.455.2).
//   * and every sample this script can load is **six subs per pointing**, so
//     even a node count would have been measured at a size where nothing can go
//     wrong. The magnitude was the blind spot, not the state.
//
// So: load the `deep` sample (`--deep`, one field shot 1,200 times), open its
// Target page, and report the three numbers that move with the rows —
//
//   * how many rows the table renders against how many subs the target has,
//   * the page's total DOM node count,
//   * and whether **scrolling** the table grows the rendered window, which is
//     the one path jsdom can never cover: it has no `IntersectionObserver`, so
//     the auto-grow in `frontend/src/frameWindow.ts` is unreachable by the unit
//     suite and reachable only from here.
//
// It is a FINDER, not a test: anything it reports still needs a real regression
// test in the suite before it counts as fixed.
import { existsSync } from "node:fs";
import { chromium } from "playwright";

// Same bundled-browser dance as dogfood_probe.mjs, and for the same reason.
const BUNDLED = [
  process.env.CHROMIUM_PATH,
  `${process.env.PLAYWRIGHT_BROWSERS_PATH || "/opt/pw-browsers"}/chromium`,
].find((p) => p && existsSync(p));

const BASE = process.env.BASE_URL || "http://127.0.0.1:8811";
const SHOTS = process.env.SHOTS_DIR || "/tmp/astrostack-dogfood/shots";
const SAFE = process.env.TARGET_SAFE || "";

if (!SAFE) {
  console.log("deep drive: no deep target — skipping");
  process.exit(0);
}
const ROUTE = `/targets/${SAFE}`;
// The table pages its frames 2,000 at a time and then renders; on a thousand-sub
// target the fetch and the first paint are both real work. Generous rather than
// tight: a false "0 rows" costs a run an investigation.
const SETTLE_MS = 20000;

const browser = await chromium.launch(BUNDLED ? { executablePath: BUNDLED } : {});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();

const errors = [];
const failures = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("response", (r) => {
  if (!r.url().startsWith(BASE)) return;
  if (r.status() >= 400) {
    failures.push(`${r.status()} ${r.request().method()} ${r.url().slice(BASE.length)}`);
  }
});

const counts = () => page.evaluate(() => {
  const body = document.querySelector('[data-testid="frames-table-body"]');
  return {
    rows: body ? body.querySelectorAll("tr").length : 0,
    nodes: document.querySelectorAll("*").length,
    foot: !!document.querySelector('[data-testid="frame-window-foot"]'),
    footText: document.querySelector('[data-testid="frame-window-foot"]')?.innerText?.trim() || "",
  };
});

// How many subs the app itself thinks this target has, so the row count is read
// against the app's own number rather than against the flag's expectation.
// Asked through playwright's own request context, NOT `page.evaluate(fetch)`:
// before the first navigation the page's origin is `null`, so an in-page fetch
// is refused by CORS and answers 0 — which would quietly disarm the
// one-row-per-sub check below and log an error that is about this drive rather
// than about the app. (Observed on this drive's first run.)
let subs = 0;
try {
  const r = await ctx.request.get(`${BASE}/api/sample`);
  subs = (await r.json()).deep_n_frames || 0;
} catch { /* reported as 0 below */ }

const t0 = Date.now();
await page.goto(`${BASE}${ROUTE}`, { waitUntil: "domcontentloaded" });
try {
  await page.waitForSelector('[data-testid="frames-table-body"] tr', { timeout: SETTLE_MS });
} catch {
  console.log("   [deep] the frames table never rendered a row — nothing measured");
}
const first = await counts();
const paintMs = Date.now() - t0;

console.log(`-- the frames table at scale (${SAFE}, ${subs} subs)`);
console.log(`   [deep] rows rendered: ${first.rows} of ${subs} subs`
            + `  ·  page DOM nodes: ${first.nodes}  ·  first paint ${paintMs} ms`);
if (subs && first.rows >= subs) {
  console.log(`   [deep] ONE ROW PER SUB — the table is unwindowed at ${subs} subs.`);
  console.log(`   [deep] That is the v0.455.2 defect back; a page-height probe`);
  console.log(`   [deep] cannot see it, which is why this drive exists.`);
}
console.log(`   [deep] window foot: ${first.foot ? JSON.stringify(first.footText) : "ABSENT"}`);

// The auto-grow. jsdom has no IntersectionObserver, so this is the only place
// the scroll path is exercised at all — a regression here reads as "the table
// stops at 300 rows and only the button gets you further", which is degraded
// rather than broken, i.e. exactly the kind of thing nobody notices.
if (first.foot) {
  await page.evaluate(() => {
    const foot = document.querySelector('[data-testid="frame-window-foot"]');
    foot?.scrollIntoView({ block: "end" });
  });
  await page.waitForTimeout(2000);
  const grown = await counts();
  console.log(`   [deep] after scrolling to the foot: ${grown.rows} rows`
              + `  ·  ${grown.nodes} nodes`
              + (grown.rows > first.rows ? "  (grew — the observer fired)"
                                         : "  (UNCHANGED — the auto-grow did not fire)"));
}

await page.screenshot({ path: `${SHOTS}/deep-target.png`, fullPage: true });

if (errors.length) console.log(`   [deep] console errors: ${errors.slice(0, 5).join(" | ")}`);
if (failures.length) console.log(`   [deep] failed requests: ${failures.slice(0, 5).join(" | ")}`);
if (!errors.length && !failures.length) console.log("   [deep] no console errors, no failed requests");

await browser.close();
