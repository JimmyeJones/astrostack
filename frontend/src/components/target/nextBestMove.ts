/** "To make this even better" — one calm, plain-language sentence naming the
 * single highest-leverage thing that would most improve this target next time.
 *
 * The app is full of *honest signals* about a finished stack — how many subs
 * combined, how many failed to plate-solve, the total integration time — but
 * they live scattered across the Target/History/QC surfaces as *numbers*, and
 * nothing tells a beginner the one thing to do differently. A non-expert who
 * shot only 15 minutes, or lost most of their subs to "not located", has no way
 * to know which lever matters most on *their* picture. That "what should I
 * change next?" is exactly the coaching a beginner wants and a pro does in their
 * head.
 *
 * This picks exactly ONE lever — the highest-priority unmet one, in a fixed sane
 * order (can't-locate-subs → too-thin → short-integration → all-good) — and says
 * it plainly, translating counts/minutes into "install the star DB / add subs /
 * add time" rather than a QC table. It never judges star sharpness against an
 * absolute bar (FWHM in pixels needs per-camera calibration to read as
 * "soft" — the deliberately-deferred soft-star lever), so it can't false-alarm.
 *
 * Pure + threshold-driven so it's trivially unit-testable. Returns `null`
 * (card hidden) when there's no finished stack to advise on, when inputs are
 * missing, or when the result is already deep and healthy — never an error.
 */

import { THIN_STACK_MAX_FRAMES } from "./thinStack";

// A plate-solve shortfall is worth flagging as the top lever only when it's both
// a real share of the session AND several subs — a stray unsolved frame or two
// isn't worth a nudge, but losing a quarter-plus of your subs to "not located"
// is usually the single biggest thing holding the stack back (they never reach
// the stacker at all).
export const LOCATE_MIN_UNSOLVED = 3;
export const LOCATE_MIN_FRACTION = 0.25;

// Below ~1 hour a deep-sky target has barely started building signal-to-noise;
// galaxies and nebulae reward multiple hours. Universal to the OSC deep-sky
// workflow, so it needs no per-camera calibration.
export const SHORT_INTEGRATION_S = 60 * 60; // 1 hour
// At/above this the stack is genuinely deep; with a healthy frame count there's
// nothing to nudge, so stay silent rather than nag a good result.
export const DEEP_INTEGRATION_S = 3 * 60 * 60; // 3 hours

export type NextBestMoveKind = "locate" | "thin" | "integration" | "good";

export interface NextBestMove {
  kind: NextBestMoveKind;
  phrase: string;
}

export interface NextBestMoveInput {
  /** Frames the latest stack actually combined (`StackRun.n_frames_used`). */
  nFramesUsed?: number | null;
  /** Total integration time in seconds (`StackRun.total_exposure_s`), if known. */
  integrationS?: number | null;
  /** Accepted subs that couldn't be plate-solved (the "unsolved" reject bucket). */
  nUnsolved?: number | null;
}

function finite(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * Pick the single highest-leverage next step for a finished stack, or `null`.
 *
 * Fixed priority ladder (only the top unmet lever ever fires):
 *   1. `locate`      — a real share of subs failed to plate-solve.
 *   2. `thin`        — barely any frames combined (also covered by the louder
 *                      thin-stack warning; kept here so the ladder is complete).
 *   3. `integration` — a healthy stack but under ~1 hour total.
 *   4. `good`        — decent result; encourage + name the one lever (time) that
 *                      still helps. Silent once the stack is genuinely deep.
 */
export function nextBestMove(input: NextBestMoveInput): NextBestMove | null {
  const nUsed = finite(input.nFramesUsed);
  // Nothing stacked yet → nothing to advise on.
  if (nUsed == null || nUsed < 0) return null;

  const nUnsolved = Math.max(0, finite(input.nUnsolved) ?? 0);
  const integrationS = finite(input.integrationS);

  // 1. Can't-locate-subs. The unsolved subs never reached the stacker, so
  //    getting them to plate-solve adds real frames — the biggest lever when a
  //    meaningful share of the session is stuck as "not located".
  const nStackable = nUsed + nUnsolved;
  if (
    nUnsolved >= LOCATE_MIN_UNSOLVED &&
    nStackable > 0 &&
    nUnsolved / nStackable >= LOCATE_MIN_FRACTION
  ) {
    return {
      kind: "locate",
      phrase:
        `Only ${nUsed} of your ${nStackable} subs were located and stacked — ` +
        `the other ${nUnsolved} couldn't be plate-solved, so they were left ` +
        `out. Installing ASTAP's star database (in Settings) usually lets far ` +
        `more of them stack, which is the biggest thing that would improve ` +
        `this picture.`,
    };
  }

  // 2. Too-thin. Barely any frames combined, so the noise never averages down.
  if (nUsed <= THIN_STACK_MAX_FRAMES) {
    return {
      kind: "thin",
      phrase:
        `This stack combined only ${nUsed} ${nUsed === 1 ? "sub" : "subs"} — ` +
        `too few to smooth out the noise. Adding more subs is the biggest win ` +
        `here; a stack only gets cleaner as it combines more frames.`,
    };
  }

  // The integration-based levers need a known total exposure. Without it, a
  // healthy stack gets no guess — stay silent rather than invent advice.
  if (integrationS == null) return null;

  // 3. Short-integration. A healthy frame count but not much total time; more
  //    hours is the lever that pulls out faint detail on deep-sky targets.
  if (integrationS < SHORT_INTEGRATION_S) {
    const mins = Math.round(integrationS / 60);
    const soFar = mins > 0 ? `${mins} min so far` : "only a few minutes so far";
    return {
      kind: "integration",
      phrase:
        `Add more time — ${soFar}. Galaxies and nebulae reward hours, so ` +
        `another clear night or two on this target would pull out much more ` +
        `faint detail.`,
    };
  }

  // Genuinely deep and healthy → nothing worth nudging; stay silent.
  if (integrationS >= DEEP_INTEGRATION_S) return null;

  // 4. All good (decent depth, but more time always still helps).
  return {
    kind: "good",
    phrase:
      `This is a solid result — plenty of subs went in. More time is the main ` +
      `thing that'll add depth from here, so keep revisiting it on clear nights.`,
  };
}
