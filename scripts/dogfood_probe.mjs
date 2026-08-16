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
//     primary button rendering as "Edit imag" (v0.263.4).
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

// The real route table (frontend/src/main.tsx) — a typo here reads as a bug
// ("Unexpected Application Error! 404 Not Found") that is entirely the probe's.
const ROUTES = [
  "/", "/library", "/gallery", "/best", "/sky-so-far", "/tonight", "/sky",
  "/telescope", "/moon-sun", "/calibration", "/combine", "/jobs", "/storage",
  "/logs", "/settings",
  ...(SAFE ? [`/targets/${SAFE}`, `/targets/${SAFE}/stack`,
              `/targets/${SAFE}/history`] : []),
  // The editor is priority 1, so it is worth a shot even though it is slow.
  ...(SAFE && RUN_ID ? [`/targets/${SAFE}/edit/${RUN_ID}`] : []),
];

const WIDTHS = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "phone", width: 420, height: 860 },
];

/** Leaf elements whose content is wider than the box drawn for it. Passed to
 * page.evaluate as a function (a *string* would be evaluated as an expression
 * and hand back the function itself), so it must not close over module scope. */
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

const browser = await chromium.launch(
  BUNDLED ? { executablePath: BUNDLED } : {},
);
let findings = 0;
for (const { name, width, height } of WIDTHS) {
  const ctx = await browser.newContext({ viewport: { width, height } });
  const page = await ctx.newPage();
  const errors = [];
  // A container with no outbound network makes the Sky Map's remote sky survey
  // fail loudly; that says nothing about this app, so it isn't a finding.
  const ours = (t) => !/https?:\/\/(?!127\.0\.0\.1|localhost)/.test(t)
    && !/ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED|HiPS/.test(t);
  page.on("pageerror", (e) => { if (ours(String(e))) errors.push(String(e)); });
  page.on("console", (m) => {
    if (m.type() === "error" && ours(m.text())) errors.push(m.text());
  });

  for (const route of ROUTES) {
    errors.length = 0;
    try {
      await page.goto(BASE + route, { waitUntil: "networkidle", timeout: 20000 });
    } catch {
      // The Sky Map keeps talking to a remote survey, so it never goes idle —
      // shoot and probe it anyway rather than skipping the page entirely.
      console.log(`[${name}] ${route}: never went network-idle; probing anyway`);
    }
    await page.waitForTimeout(400);   // let self-hiding cards make their minds up
    const slug = route.replace(/\W+/g, "_") || "root";
    await page.screenshot({
      path: `${SHOTS}/${name}${slug}.png`, fullPage: true,
    });
    const over = await page.evaluate(overflowingLeaves);
    for (const o of over) {
      findings++;
      console.log(
        `[${name}] ${route}: OVERFLOW <${o.tag}> ${o.clientWidth}px box vs ` +
        `${o.scrollWidth}px content — "${o.text}" (${o.cls})`,
      );
    }
    for (const e of errors.slice(0, 3)) {
      findings++;
      console.log(`[${name}] ${route}: CONSOLE ERROR ${e.slice(0, 200)}`);
    }
  }
  await ctx.close();
}
await browser.close();
console.log(findings ? `${findings} thing(s) to look at` : "nothing overflowing, no console errors");
