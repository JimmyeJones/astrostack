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
 * The plain-language caution for "min/max rejection + quality weighting", or
 * `null` when the two don't actually conflict.
 */
export function minMaxIgnoresWeightingHint(input: WeightingHintInput): string | null {
  const { minMaxReject, qualityWeighted, drizzle, frames } = input;
  if (!minMaxReject || !qualityWeighted || drizzle) return null;
  // A known-small stack keeps its weights (the engine's n >= 3 gate), so say
  // nothing; an unknown count (frames === null) is worded conditionally below.
  if (frames !== null && frames < WEIGHTING_MIN_MAX_MIN_FRAMES) return null;

  const lead = frames === null
    ? `On any stack of ${WEIGHTING_MIN_MAX_MIN_FRAMES} or more subs, min/max rejection and quality weighting don't combine`
    : "Min/max rejection and quality weighting don't combine";
  return `${lead}: min/max is an order statistic (it drops the highest and lowest values at each pixel), so it ignores per-frame weights — your quality weighting won't affect ${frames === null ? "those stacks" : "this stack"}. Use sigma clipping if you want quality weighting to count, or keep min/max and turn quality weighting off.`;
}
