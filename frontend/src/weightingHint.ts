// Min/max rejection and quality weighting don't combine: MinMaxRejectAccumulator
// is an order statistic (it drops the k highest/lowest values at each pixel), so
// it ignores per-frame weights entirely. The engine's gate is
// `weights_applied = not (min_max_reject and not drizzle and n >= 3)`
// (`seestack/stack/stacker.py`) — mirrored here so the pick-time caution and the
// engine agree. Advisory only; it never blocks a stack or a save.
//
// This lives on its own so the per-target Stack form (which knows the frame
// count) and the global stack defaults in Settings (which don't) share one
// wording instead of drifting apart — the same drift that cost v0.237.1 a fix.

/** Below this many frames the engine keeps weights even with min/max on. */
export const WEIGHTING_MIN_MAX_MIN_FRAMES = 3;

export type WeightingHintInput = {
  minMaxReject: boolean;
  qualityWeighted: boolean;
  drizzle: boolean;
  /**
   * Frames this stack will actually combine, or `null` when the count isn't
   * knowable yet (the global defaults apply to whatever a future run brings).
   */
  frames: number | null;
};

/**
 * Does the combine that ran (or will run) ignore this stack's quality weighting?
 *
 * The gate itself, split out of the sentence below so a *finished* run's chip
 * and a pre-run caution cannot disagree about one stack. `frames === null`
 * means "not knowable" and answers **true** conditionally — the wording that
 * consumes it says "on any stack of 3 or more subs" rather than making a claim
 * about a particular one.
 *
 * Pass a count that can only *understate* the dispatcher's own `n` (the frames
 * that actually combined, say): the engine asks `n >= 3` of its candidate
 * frames, so understating can only make this answer `false`, i.e. leave a
 * surface saying what it says today. Overstating would invent a "your weighting
 * didn't count" on a stack where it did.
 */
export function minMaxIgnoresWeighting(input: WeightingHintInput): boolean {
  const { minMaxReject, qualityWeighted, drizzle, frames } = input;
  if (!minMaxReject || !qualityWeighted || drizzle) return false;
  // A known-small stack keeps its weights (the engine's n >= 3 gate: below it
  // `MinMaxRejectAccumulator` falls through to a plain weighted mean).
  if (frames !== null && frames < WEIGHTING_MIN_MAX_MIN_FRAMES) return false;
  return true;
}

/** Chip label for a *finished* run whose combine ignored its weighting.
 *
 * Deliberately the same 16 characters as the "Quality-weighted" chip it stands
 * in for: a longer chip pushes its neighbours off the Gallery card's badge row
 * (the v0.438.3 lesson), and this one has to fit beside "min-max" and
 * "Gradient removal" on a 280 px card. */
export const WEIGHTING_UNUSED_LABEL = "Weighting unused";

/**
 * …and the sentence behind that chip, in the past tense a finished picture
 * wants. `minMaxIgnoresWeightingHint` is the same fact worded for a stack that
 * has not run yet, which is why this is a sibling rather than a reuse: "your
 * quality weighting won't affect this stack" reads as a warning you can still
 * act on, and on a Gallery card the stack is already made.
 *
 * Says what the run recorded (the engine stamps `WGTSKIP` on exactly this
 * path), why, and the one thing that would change it next time — the same three
 * beats History's own `weightingSkippedText` uses on the run-info panel, so the
 * two surfaces describing one picture agree.
 */
export function weightingUnusedNote(frames: number | null): string {
  const count = frames === null ? "these subs" : `${frames} subs`;
  return (
    `Quality weighting was on, but this stack combined ${count} with min/max`
    + " rejection — an order statistic, which drops the highest and lowest value"
    + " at each pixel and ignores per-frame weights entirely, so the weighting"
    + " made no difference to this picture. Stack again with sigma clipping"
    + " instead if you want it to count."
  );
}

/**
 * The plain-language caution for "min/max rejection + quality weighting", or
 * `null` when the two don't actually conflict.
 */
export function minMaxIgnoresWeightingHint(input: WeightingHintInput): string | null {
  if (!minMaxIgnoresWeighting(input)) return null;
  const { frames } = input;

  const lead = frames === null
    ? `On any stack of ${WEIGHTING_MIN_MAX_MIN_FRAMES} or more subs, min/max rejection and quality weighting don't combine`
    : "Min/max rejection and quality weighting don't combine";
  return `${lead}: min/max is an order statistic (it drops the highest and lowest values at each pixel), so it ignores per-frame weights — your quality weighting won't affect ${frames === null ? "those stacks" : "this stack"}. Use sigma clipping if you want quality weighting to count, or keep min/max and turn quality weighting off.`;
}
