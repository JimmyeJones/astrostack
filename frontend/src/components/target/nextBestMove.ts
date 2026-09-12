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
 * order (can't-locate-subs → too-thin → soft-stars → short-integration →
 * all-good) — and says it plainly, translating counts/minutes into "install the
 * star DB / add subs / refocus / add time" rather than a QC table. It never
 * judges star sharpness against an absolute bar (FWHM in pixels needs per-camera
 * calibration to read as "soft"); the soft-star rung fires only on a *relative*
 * signal — this target's newest stack being softer than its own history (see
 * `softStars.ts`) — so it can't false-alarm across camera models.
 *
 * Pure + threshold-driven so it's trivially unit-testable. Returns `null`
 * (card hidden) when there's no finished stack to advise on, when inputs are
 * missing, or when the result is already deep and healthy — never an error.
 */

import { THIN_STACK_MAX_FRAMES } from "./thinStack";
import { fieldsOfSkyLabel, perPixel, spansMoreThanOneField } from "./perPixel";
import { formatIntegration } from "../../format";
import { settingsLink } from "../../settingsSections";
import {
  goalDifficultyFactor,
  goalHoursForType,
  type GoalDifficulty,
} from "../../readiness";
import { objectTypeBucket } from "../../tonight";
import type { SoftStars } from "./softStars";

// A plate-solve shortfall is worth flagging as the top lever only when it's both
// a real share of the session AND several subs — a stray unsolved frame or two
// isn't worth a nudge, but losing a quarter-plus of your subs to "not located"
// is usually the single biggest thing holding the stack back (they never reach
// the stacker at all).
export const LOCATE_MIN_UNSOLVED = 3;
export const LOCATE_MIN_FRACTION = 0.25;

// Below ~1 hour a deep-sky target has barely started building signal-to-noise;
// galaxies and nebulae reward multiple hours.
//
// Both of these bars are **per-pixel** quantities — "how much light has landed
// where I am looking?" — so on a mosaic they are compared against the run's
// integration divided by the sky its canvas covers (`perPixel.ts`), not against
// the target's total. Read off the total, a 12x8 raster at 3 h is "genuinely
// deep" at under two minutes a panel, and the card goes silent on a picture
// whose single biggest lever is more time. A single field is unaffected: there
// the two figures are the same number.
export const SHORT_INTEGRATION_S = 60 * 60; // 1 hour
// At/above this the stack is genuinely deep; with a healthy frame count there's
// nothing to nudge, so stay silent rather than nag a good result.
export const DEEP_INTEGRATION_S = 3 * 60 * 60; // 3 hours

// …and those two numbers are not independent constants: they are the readiness
// card's own ladder boundaries, evaluated at its default goal. `readiness.ts`
// calls a target "a good start" below **0.25** of its goal and "nearly there"
// at **0.75**, and the goal for an unclassified/nebula target is **4 h** — so
// 0.25 x 4 h = 1 h is exactly `SHORT_INTEGRATION_S` and 0.75 x 4 h = 3 h is
// exactly `DEEP_INTEGRATION_S`. The ladder was written for that one bucket and
// then applied to every object, which is how the same page came to say two
// things about one target: a star cluster (goal 1.5 h) at 50 min was "nearly
// there" on the readiness card and "add more time — galaxies and nebulae reward
// hours, so another clear night or two" here, and a galaxy (goal 6 h) at 1.2 h
// was "a good start" there and "a solid result — plenty of subs went in" here.
//
// So express the bars where they came from: the same fractions of the same
// per-type goal `readiness.ts` and `mosaicEffort.ts` already judge against.
// Omitting the type yields the `Other` bucket's 4 h, i.e. 1 h / 3 h — today's
// numbers, bit for bit, for every caller that has no catalogue match.
export const SHORT_INTEGRATION_FRACTION = 0.25;
export const DEEP_INTEGRATION_FRACTION = 0.75;

/** The two per-pixel bars (seconds) this ladder judges `type` against.
 *
 * `difficulty` is the target's vetted "how hard for a Seestar?" verdict, passed
 * straight through to `goalHoursForType`: the bars are fractions of the goal, so
 * a goal the badge two inches up the page has sharpened has to carry them with
 * it — otherwise this ladder disagrees with the readiness card again, in the
 * other direction from the one v0.429.2 closed. Omit it and the bars are exactly
 * the per-type ones. */
export function integrationBars(
  type: string | null | undefined,
  difficulty?: GoalDifficulty,
): {
  shortS: number;
  deepS: number;
} {
  const goalS = goalHoursForType(type, difficulty) * 3600;
  return {
    shortS: goalS * SHORT_INTEGRATION_FRACTION,
    deepS: goalS * DEEP_INTEGRATION_FRACTION,
  };
}

export type NextBestMoveKind = "locate" | "thin" | "soft" | "integration" | "good";

export interface NextBestMove {
  kind: NextBestMoveKind;
  phrase: string;
  /** Where to go and do it, when the phrase names something that lives on
   * another screen — so "in Settings" is a tap rather than a hunt through seven
   * sections. Same shape as `StackHealthCard`'s `noteAction`. */
  action?: { label: string; href: string };
}

export interface NextBestMoveInput {
  /** Frames the latest stack actually combined (`StackRun.n_frames_used`). */
  nFramesUsed?: number | null;
  /** Total integration time in seconds (`StackRun.total_exposure_s`), if known. */
  integrationS?: number | null;
  /** Accepted subs that couldn't be plate-solved (the "unsolved" reject bucket). */
  nUnsolved?: number | null;
  /** Relative star-softness signal vs this target's own history, if computable
   * (from `softerThanUsual(runs)`). Present only when the newest stack came out
   * materially softer than usual; drives the "refocus" rung. */
  softStars?: SoftStars | null;
  /** How many single-frame field-fulls of sky the stack's canvas covers
   * (`StackRun.field_fulls`). Omit / null / ≤1 on a single field and on any
   * caller without the figure — the ladder is then exactly what it was. */
  fieldFulls?: number | null;
  /** The catalogue object type from the identify card ("Open Cluster",
   * "Galaxy", …), so the two time rungs are judged against the same per-type
   * goal the readiness card beside them uses, and the advice names the right
   * kind of object. Omit / null / unrecognised → the `Other` bucket, which is
   * today's 1 h / 3 h ladder exactly. */
  objectType?: string | null;
  /** The target's vetted difficulty verdict, when the caller has one — the same
   * `DifficultyHint` the badge on this page renders. It sharpens the per-type
   * goal the two rungs are fractions of (see `integrationBars`). Omit / null /
   * an un-curated verdict → today's per-type ladder, unchanged. */
  difficulty?: GoalDifficulty;
}

function finite(v: number | null | undefined): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/**
 * Pick the single highest-leverage next step for a finished stack, or `null`.
 *
 * Fixed priority ladder (only the top unmet lever ever fires):
 *   1. `locate`      — a real share of subs failed to plate-solve.
 *   2. `thin`        — barely any subs on any one part of the picture (also
 *                      covered by the louder thin-stack warning; kept here so
 *                      the ladder is complete).
 *   3. `soft`        — a healthy stack whose stars came out softer than usual for
 *                      this target (relative to its own history) → check focus.
 *   4. `integration` — a healthy stack but under a quarter of this object
 *                      type's integration goal, *per pixel* (~1 h for a
 *                      nebula or an unrecognised target; see `integrationBars`).
 *   5. `good`        — decent result; encourage + name the one lever (time) that
 *                      still helps. Silent once the stack is genuinely deep.
 */
export function nextBestMove(input: NextBestMoveInput): NextBestMove | null {
  const nUsed = finite(input.nFramesUsed);
  // Nothing stacked yet → nothing to advise on.
  if (nUsed == null || nUsed < 0) return null;

  const nUnsolved = Math.max(0, finite(input.nUnsolved) ?? 0);
  const integrationS = finite(input.integrationS);
  // On a mosaic the two "how much have I got?" rungs below are asked of one
  // part of the picture, not of the target — see the constants above.
  const mosaic = spansMoreThanOneField(input.fieldFulls);
  const depth = mosaic ? Math.round(perPixel(nUsed, input.fieldFulls)) : nUsed;
  const perPixelS =
    integrationS == null ? null : perPixel(integrationS, input.fieldFulls);
  // "How much is enough here?" is the readiness card's question, so take its
  // answer rather than a second one — see `integrationBars` above.
  const bars = integrationBars(input.objectType, input.difficulty);

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
      action: {
        label: "Check your star database in Settings \u2192",
        href: settingsLink("plate-solving"),
      },
    };
  }

  // 2. Too-thin. Barely any subs on any one part of the picture, so the noise
  //    never averages down there.
  if (depth <= THIN_STACK_MAX_FRAMES) {
    return {
      kind: "thin",
      phrase: mosaic
        ? `Your ${nUsed} subs are spread across ${fieldsOfSkyLabel(input.fieldFulls)}, ` +
          `so each part of this picture has only about ${depth} ` +
          `${depth === 1 ? "sub" : "subs"} on it — too few to smooth out the ` +
          `noise. More passes over the same mosaic is the biggest win here; ` +
          `a stack only gets cleaner as it combines more frames.`
        : `This stack combined only ${depth} ${depth === 1 ? "sub" : "subs"} — ` +
          `too few to smooth out the noise. Adding more subs is the biggest win ` +
          `here; a stack only gets cleaner as it combines more frames.`,
    };
  }

  // 3. Soft-stars. A healthy stack, but its stars came out softer than this
  //    target's own usual (a relative signal — no absolute px bar, so no
  //    per-camera calibration needed). A quick refocus next session is the
  //    highest-leverage fix — it tightens every future sub — so it outranks the
  //    add-time nudges below. Only ever fires on a real regression vs history.
  if (input.softStars) {
    const now = input.softStars.currentFwhmPx.toFixed(1);
    const usual = input.softStars.typicalFwhmPx.toFixed(1);
    return {
      kind: "soft",
      phrase:
        `Your stars came out a little softer than usual on this one — about ` +
        `${now} px across, vs your typical ${usual} px for this target. A quick ` +
        `refocus at the start of your next session usually tightens them back ` +
        `up, which sharpens every sub you shoot.`,
    };
  }

  // The integration-based levers need a known total exposure. Without it, a
  // healthy stack gets no guess — stay silent rather than invent advice.
  if (integrationS == null || perPixelS == null) return null;

  // 3. Short-integration. A healthy frame count but not much light where the
  //    beginner is looking; more hours is the lever that pulls out faint detail
  //    on deep-sky targets.
  if (perPixelS < bars.shortS) {
    const mins = Math.round(perPixelS / 60);
    const soFar = mins > 0 ? `${mins} min so far` : "only a few minutes so far";
    // A cluster is the one bucket where "galaxies and nebulae reward hours" is
    // simply not a fact about the thing on screen: `target_difficulty` calls
    // clusters "uniformly easy — bright point sources that need no integration
    // to look good", and their goal is the shortest the app has. Asking for
    // "another clear night or two" there contradicts the badge two inches up
    // the page saying it looks good in well under an hour, so say the true
    // thing and name the smaller lever it actually needs.
    //
    // …and a cluster is only *one* of the things that earn that badge. The words
    // quoted above are `target_difficulty`'s **easy** verdict, which every
    // curated-easy nebula and galaxy prints too — M42, M31, the Blue Snowball,
    // the Cat's Eye — and this branch never asked. Photographed on the bundled
    // M42 sample: the coaching card read "Galaxies and nebulae reward hours, so
    // another clear night or two on this target" with "It usually looks good in
    // well under an hour" in the object card below it, and the readiness card
    // between them quoting a goal of ~2 h — a night or two being several times
    // the whole goal.
    //
    // So ask the question once, from the two classifications that already
    // exist rather than from a new threshold: the type rule (clusters are
    // uniformly easy) and the curated verdict. `goalDifficultyFactor` is the
    // very function the goal these bars are fractions of is scaled by, so this
    // rung and that goal cannot come to different opinions about one object; it
    // returns 1 for an un-curated verdict, an unknown level, and an older
    // backend, all of which leave this phrase exactly as it was.
    const cluster = objectTypeBucket(input.objectType) === "Cluster";
    const curatedEasy = goalDifficultyFactor(input.difficulty) < 1;
    // Spelled as one subject so the Cluster sentences stay byte-for-byte what
    // they have said since v0.429.2 — only the set of targets that get them
    // grows.
    const quickly = cluster
      ? "Clusters come up quickly"
      : "This one comes up quickly for a Seestar";
    return {
      kind: "integration",
      phrase: mosaic
        ? `Add more time — your ${formatIntegration(integrationS)} is spread across ` +
          `${fieldsOfSkyLabel(input.fieldFulls)}, so each part of this picture ` +
          `has ${soFar}. ` +
          (cluster || curatedEasy
            ? `${quickly}, so even another pass or two over the ` +
              `same mosaic would clean up the background.`
            : `Galaxies and nebulae reward hours, so more passes over ` +
              `the same mosaic would pull out much more faint detail.`)
        : `Add more time — ${soFar}. ` +
          (cluster || curatedEasy
            ? `${quickly}, so even the rest of one clear night on ` +
              `this target would clean up the background nicely.`
            : `Galaxies and nebulae reward hours, so another clear night or two ` +
              `on this target would pull out much more faint detail.`),
    };
  }

  // Genuinely deep and healthy → nothing worth nudging; stay silent.
  if (perPixelS >= bars.deepS) return null;

  // 4. All good (decent depth, but more time always still helps).
  return {
    kind: "good",
    phrase:
      `This is a solid result — plenty of subs went in. More time is the main ` +
      `thing that'll add depth from here, so keep revisiting it on clear nights.`,
  };
}
