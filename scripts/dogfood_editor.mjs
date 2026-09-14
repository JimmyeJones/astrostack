// Drive the EDITOR, rather than photograph it.
//
// `dogfood_probe.mjs` visits `/targets/<t>/edit/<run>` and screenshots it, which
// is worth doing but only ever sees the editor in the one state it opens in:
// whatever recipe the run already carries, before anybody touches a control.
// Priority 1 (AGENTS.md §1) is the editor, and the owner's standing complaints
// about it — "a live preview that doesn't match/behave, clunky and confusing
// controls" — are all about what happens *after* a click. Nothing in this repo's
// tooling had ever clicked one.
//
// So this one adds every operation the Add menu offers, one at a time, and after
// each asks three questions a screenshot cannot:
//
//   * did the live preview actually re-render? (an op that renders nothing is
//     the "the preview must show every enabled action" bug, v0.57.0's class);
//   * did the browser log an error — a thrown render, a bad prop, a crashed
//     parameter panel;
//   * did any of this app's own requests fail (4xx/5xx) while the op was on?
//
// Then it undoes and redoes, because the history stack is the other thing only
// interaction reaches.
//
// Run it through `scripts/agent-dogfood.sh` (which boots the app, loads and
// stacks the sample, and installs playwright into a scratch dir first) — the
// `--editor` flag, or directly with BASE_URL / SHOTS_DIR / TARGET_SAFE /
// TARGET_RUN_ID set.
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
const RUN_ID = process.env.TARGET_RUN_ID || "";

if (!SAFE || !RUN_ID) {
  console.log("editor drive: no stacked target to edit — skipping");
  process.exit(0);
}
const ROUTE = `/targets/${SAFE}/edit/${RUN_ID}`;

// A preview render is a server-side job on the real canvas, and the ops flagged
// `heavy` (deconvolution, denoise) deliberately debounce longer. These are
// generous rather than tight: a false "UNCHANGED" costs a run an investigation.
const SETTLE_MS = 7000;
const IDLE_MS = 25000;

const browser = await chromium.launch(BUNDLED ? { executablePath: BUNDLED } : {});
const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await ctx.newPage();

let errors = [];
let failures = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("response", (r) => {
  // Only this app's own calls: a container with no outbound network makes
  // remote survey tiles fail, which says nothing about the editor.
  if (!r.url().startsWith(BASE)) return;
  if (r.status() >= 400) {
    failures.push(`${r.status()} ${r.request().method()} ${r.url().slice(BASE.length)}`);
  }
});

let findings = 0;
/** Report and clear whatever the page complained about since the last call. */
function drain(tag) {
  for (const e of errors) console.log(`  ! ${tag}: CONSOLE ERROR ${e.slice(0, 220)}`);
  for (const f of failures) console.log(`  ! ${tag}: FAILED REQUEST ${f.slice(0, 180)}`);
  findings += errors.length + failures.length;
  errors = [];
  failures = [];
}

/** The live preview's current source. It is re-fetched (a new object URL) on
 * every render, so a value that doesn't move means the preview didn't. */
const previewSrc = () => page.evaluate(() => {
  const img = document.querySelector('img[alt="preview"]');
  return img ? img.currentSrc || img.src : null;
});

/** Wait for the debounced preview to settle. `networkidle` alone isn't enough —
 * the editor polls while a render job runs — so settle, then idle, then settle. */
async function settle() {
  await page.waitForTimeout(SETTLE_MS);
  try {
    await page.waitForLoadState("networkidle", { timeout: IDLE_MS });
  } catch { /* a poll can keep the socket warm; the timeout is the answer */ }
  await page.waitForTimeout(1200);
}

await page.goto(BASE + ROUTE, { waitUntil: "networkidle", timeout: 90000 });
await page.waitForTimeout(2500);
console.log(`editor drive: ${ROUTE}`);
drain("open");
await page.screenshot({ path: `${SHOTS}/editor-00-open.png`, fullPage: true });

const opened = await previewSrc();
if (!opened) {
  findings++;
  console.log("  ! open: no live preview image rendered");
}

// ---- "Check it at full size" ----------------------------------------------
//
// The control is gated on `proxy_scale > 1`, i.e. on a canvas past the editor's
// 1500 px proxy cap — which no bundled sample produced until `--big` (v0.446.0).
// So for its whole life the modal behind it, its navigator, its marker, its
// `X-Loupe-Window` header and its split comparison were reachable by nobody:
// this drive adds every op in the Add menu and never saw the button, and the
// page probe photographs one state and cannot click. It is ~250 lines of the
// priority-1 screen whose only coverage is jsdom.
//
// The button's absence is *correct* on a small stack, so a pass that does not
// reach it says so rather than reporting nothing — the same reason the shell
// prints `location_source` and the `proxy_scale` it measured.
async function driveFullSizeCheck() {
  const unavailable = page.getByTestId("full-size-check-unavailable");
  const open = page.getByTestId("full-size-check-open");
  if (!(await open.count())) {
    if (await unavailable.count()) {
      // A geometry refusal: the control is gone and the advisories asking the
      // reader to use it are still speaking. v0.445.2 exists for this state.
      console.log(`full-size check: withheld — "${(await unavailable.first().innerText()).trim()}"`);
    } else {
      console.log("full-size check: not offered (preview is 1:1 — run with --big to reach it)");
    }
    return;
  }

  await open.first().click();
  await page.waitForTimeout(600);
  // The window is a real full-resolution render on the request path, not a
  // cached blob — give it room, then say what it drew.
  const shot = page.getByTestId("full-size-check-image");
  try {
    await shot.waitFor({ state: "visible", timeout: 45000 });
  } catch {
    findings++;
    const err = page.getByTestId("full-size-check-error");
    const why = (await err.count()) ? (await err.first().innerText()).trim() : "no image and no error";
    console.log(`  ! full-size check: the window never rendered — ${why}`);
  }
  await page.waitForTimeout(800);
  drain("full-size check (open)");

  // Read the modal as ONE paragraph, the way the shell reads the mosaic's
  // notes: three sentences about one window, written in three files.
  for (const [tag, id] of [
    ["caption", "full-size-check-caption"],
    ["where", "full-size-check-where"],
    ["split", "full-size-check-split-caption"],
  ]) {
    const el = page.getByTestId(id);
    if (await el.count()) {
      console.log(`   [${tag}] ${(await el.first().innerText()).trim().replace(/\s+/g, " ")}`);
    }
  }
  for (const id of ["full-size-check-navigator", "full-size-check-marker"]) {
    if (!(await page.getByTestId(id).count())) {
      findings++;
      console.log(`  ! full-size check: ${id} is missing from the open modal`);
    }
  }
  await page.screenshot({ path: `${SHOTS}/editor-loupe-01-open.png`, fullPage: true });

  // Move the window: the navigator is the modal's only control, and "did the
  // marker follow the click?" is a question only a browser can answer.
  const nav = page.getByTestId("full-size-check-navigator");
  if (await nav.count()) {
    const before = await page.evaluate(() => {
      const m = document.querySelector('[data-testid="full-size-check-marker"]');
      return m ? m.getAttribute("style") : null;
    });
    const box = await nav.first().boundingBox();
    if (box) {
      // A corner, not the centre: the window is clamped inside the canvas, so
      // a corner click is also the case where the clamp does something.
      await page.mouse.click(box.x + box.width * 0.15, box.y + box.height * 0.2);
      await page.waitForTimeout(6000);
      const after = await page.evaluate(() => {
        const m = document.querySelector('[data-testid="full-size-check-marker"]');
        return m ? m.getAttribute("style") : null;
      });
      if (!after) {
        findings++;
        console.log("  ! full-size check: the marker vanished after moving the window");
      } else if (after === before) {
        findings++;
        console.log("  ! full-size check: clicking the navigator did not move the window marker");
      } else {
        console.log("full-size check: the window followed a click on the navigator");
      }
      const where = page.getByTestId("full-size-check-where");
      if (await where.count()) {
        console.log(`   [where, moved] ${(await where.first().innerText()).trim()}`);
      }
      drain("full-size check (moved)");
    }
  }

  // …and the split, which is a second thing behind a click behind a click.
  const toggle = page.getByTestId("full-size-check-split-toggle");
  if (!(await toggle.count())) {
    console.log("full-size check: no preview comparison offered for this window");
  } else {
    await toggle.first().click();
    await page.waitForTimeout(1500);
    for (const id of ["full-size-check-split-before", "full-size-check-split-divider"]) {
      if (!(await page.getByTestId(id).count())) {
        findings++;
        console.log(`  ! full-size check: ${id} missing after turning the comparison on`);
      }
    }
    const cap = page.getByTestId("full-size-check-split-caption");
    if (await cap.count()) {
      console.log(`   [split] ${(await cap.first().innerText()).trim().replace(/\s+/g, " ")}`);
    }
    // Drag the divider: the one interaction in the modal with pointer capture.
    const win = page.getByTestId("full-size-check-window");
    const wbox = (await win.count()) ? await win.first().boundingBox() : null;
    if (wbox) {
      await page.mouse.move(wbox.x + wbox.width * 0.5, wbox.y + wbox.height * 0.5);
      await page.mouse.down();
      await page.mouse.move(wbox.x + wbox.width * 0.25, wbox.y + wbox.height * 0.5, { steps: 8 });
      await page.mouse.up();
      await page.waitForTimeout(800);
    }
    await page.screenshot({ path: `${SHOTS}/editor-loupe-02-split.png`, fullPage: true });
    drain("full-size check (split)");
  }

  await page.keyboard.press("Escape");
  await page.waitForTimeout(600);
  drain("full-size check (closed)");
}

await driveFullSizeCheck();

/** Every op the Add menu offers, as `{index, label}` in menu order.
 *
 * Read from the open menu rather than from a hard-coded list, so an op added
 * later is driven without editing this file. Two things about that menu matter:
 * it opens on a curated **Common** shortlist behind a "More operations" toggle
 * (so the toggle has to be clicked first, and then excluded), and each item's
 * `textContent` is the label *plus* its help line and any "slower preview"
 * chip — hence reading the label off the item's first `<p>` instead. Common ops
 * appear twice once the list is expanded (in Common and again under their
 * group), so items are addressed by **index**: the same label would be
 * ambiguous, and the list is static once expanded. The duplicates are then
 * dropped — both entries call the same `addOp(spec)` with the same spec, so
 * driving each op twice buys nothing but a doubled log and a doubled runtime.
 */
async function readAddMenu() {
  await page.getByRole("button", { name: "Add operation" }).click();
  await page.waitForTimeout(500);
  // Expand to the full list — a no-op if a previous pass already expanded it.
  const more = page.locator("[role='menuitem']", { hasText: "More operations" });
  if (await more.count()) {
    await more.first().click();
    await page.waitForTimeout(400);
  }
  const items = await page.evaluate(() =>
    [...document.querySelectorAll("[role='menuitem']")].map((el, i) => {
      const group = el.querySelector('[class*="mantine-Group-root"]');
      const first = (group || el).querySelector("p");
      return { index: i, label: ((first || el).textContent || "").trim() };
    }).filter((it) => it.label
      && !/^(More|Fewer) operations$/.test(it.label)));
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  const seen = new Set();
  return items.filter((it) => !seen.has(it.label) && seen.add(it.label));
}

const ops = await readAddMenu();
console.log(`Add menu offers ${ops.length} ops: ${ops.map((o) => o.label).join(" | ")}`);

for (const { index, label } of ops) {
  const before = await previewSrc();
  await page.getByRole("button", { name: "Add operation" }).click();
  await page.waitForTimeout(500);
  const item = page.locator("[role='menuitem']").nth(index);
  try {
    await item.click({ timeout: 5000 });
  } catch {
    findings++;
    console.log(`  ! ${label}: its Add-menu item could not be clicked`);
    await page.keyboard.press("Escape");
    continue;
  }
  await settle();
  const after = await previewSrc();
  // Geometry ops with identity defaults (a full-frame crop, ×1 resize, 0°
  // rotate) legitimately render the same picture, so they are reported rather
  // than counted — an op that *should* change the picture and doesn't is the
  // finding, and only a human reading the list can tell the two apart.
  const changed = !!after && after !== before;
  console.log(`${label}: preview ${changed ? "re-rendered" : "unchanged (identity default?)"}`);
  drain(label);
  await page.screenshot({
    path: `${SHOTS}/editor-op-${label.replace(/\W+/g, "_")}.png`, fullPage: true,
  });
  // Take it back off, so op N is measured against the same recipe as op 1
  // rather than against a nine-deep pile of everything before it. The new op is
  // NOT necessarily last — `addOp` inserts it on the correct side of the stretch
  // (`insertOnCorrectSide`) — but it *is* the selected row, which is the one
  // carrying `aria-pressed="true"`. Removing by position would delete somebody
  // else's op and quietly invalidate every reading after it.
  const remove = page.locator('[aria-pressed="true"] [aria-label="Remove"]');
  if (await remove.count()) {
    await remove.first().click();
    await settle();
    drain(`${label} (removed)`);
  } else {
    findings++;
    console.log(`  ! ${label}: added, but no selected row to remove it from`);
  }
}

// Undo/redo — the other thing only interaction reaches. Both are disabled at the
// ends of the history stack, and Playwright's click *waits* for an enabled
// element, so a disabled one would hang the drive rather than skip a step.
for (const name of ["Undo", "Redo"]) {
  const button = page.getByRole("button", { name, exact: true }).first();
  if (await button.count() && await button.isEnabled()) {
    await button.click();
    await settle();
    console.log(`${name}: applied`);
    drain(name);
  } else {
    console.log(`${name}: unavailable at this point in the history`);
  }
}

await page.screenshot({ path: `${SHOTS}/editor-99-end.png`, fullPage: true });
await browser.close();
console.log(findings ? `\n${findings} thing(s) to look at` : "\neditor drive clean");
