/** What the page behind the content should be — the two decisions the night-sky
 * theme makes, as pure functions so they can be asserted without a DOM.
 *
 * **Why a route can refuse the sky.** Two kinds of page must not have a tinted or
 * moving background:
 *
 *  - **The picture-judging surfaces** (`Editor`, `Compare`). A tint shifts how
 *    colour and background level are *perceived*, which is why PixInsight and
 *    Photoshop surround an image with neutral grey, and the editor is PRIORITY 1.
 *    The image panes themselves already paint `#000`; this keeps everything
 *    *beside* them plain dark neutral too.
 *  - **The three.js routes** (`Sky`, `Universe`), which draw their own sky and
 *    should not pay for ours a second time behind it.
 *
 * Everything else gets the deep-navy sky. The starfield is a further opt-out on
 * top of that (`prefs.ts`) — turning it off leaves the dark sky, not today's grey.
 */

export type Surround = "sky" | "neutral";
export type SkyMotion = "drifting" | "still";

/** Route prefixes that keep a neutral surround. Exact match or a `/`-delimited
 * prefix, so `/compare` and `/compare/anything` both qualify while a future
 * `/comparisons` would not. */
const NEUTRAL_PREFIXES = ["/compare", "/sky", "/universe"];

/** `/targets/<safe>/edit/<runId>` — the editor, whose `safe` name is arbitrary,
 * so it is matched by shape rather than by prefix. */
const EDITOR_PATH = /^\/targets\/[^/]+\/edit(\/|$)/;

export function surroundForPath(pathname: string): Surround {
  // Tolerate a missing or trailing-slash path: "" and "/" are the Dashboard.
  const path = pathname && pathname !== "/" ? pathname.replace(/\/+$/, "") : "/";
  if (EDITOR_PATH.test(path)) return "neutral";
  for (const prefix of NEUTRAL_PREFIXES) {
    if (path === prefix || path.startsWith(`${prefix}/`)) return "neutral";
  }
  return "sky";
}

/** The stars are drawn only where the sky is, and only if this device wants them. */
export function starfieldShown(surround: Surround, enabled: boolean): boolean {
  return surround === "sky" && enabled;
}

/** Stars sit still when the reader asked for less motion, and while the tab is
 * hidden — a background animation nobody is looking at is pure battery. */
export function skyMotion(reducedMotion: boolean, hidden: boolean): SkyMotion {
  return reducedMotion || hidden ? "still" : "drifting";
}
