/**
 * Whether the Stack form may keep the sizing it is already showing while the
 * next one loads.
 *
 * The estimate query's key carries every knob on the form — the drizzle scale,
 * κ, sigma clipping, the min/max count, "Auto outlier removal" — because the
 * *answer* genuinely differs for each. So every nudge of any of them is a new
 * key, and without a placeholder `estimate.data` goes `undefined` for the
 * duration of the request. Everything downstream of it is derived from that one
 * value: the sizing line, the time estimate, the memory verdict and its
 * one-click fix, the print plan, the per-pixel cautions, the rejection-reach
 * note, the drizzle nudge. They all vanish together and come back together, so
 * dragging the κ slider makes the entire advice block under it blink — on the
 * §1 owner's largest target, for about a second a tick, because the server was
 * rebuilding a canvas those knobs cannot move. `webapp.estimate_cache`
 * (v0.424.2) took that to ~130 ms; this is the other half, and the two are
 * worth having together: a fast answer that still blanks the panel first reads
 * as a flicker rather than as a form keeping up.
 *
 * **But only for the same target.** A placeholder is the *previous* answer,
 * and react-router does not remount this route when only the `:safe` param
 * changes — so walking from one target's Stack page to another's would leave
 * the first target's frame count and canvas size sitting under the second
 * one's title until the request lands. Showing the knob values you just moved
 * away from is honest (it is this picture, a moment ago); showing another
 * target's is not. Hence this predicate rather than a bare
 * `placeholderData: keepPreviousData`.
 */

/** The first element of the estimate query's key — see `routes/Stack.tsx`. */
export const STACK_ESTIMATE_QUERY_KEY = "stack-estimate";

/**
 * True when a held estimate is about `safe` and so may stand in while the next
 * one loads. Defensive about the key's shape: anything that is not this
 * query's own `[key, safe, …]` answers `false`, which degrades to today's
 * behaviour (a blank panel) rather than to a wrong one.
 */
export function estimateIsForTarget(
  previousKey: readonly unknown[] | undefined,
  safe: string,
): boolean {
  if (!previousKey || previousKey.length < 2) return false;
  if (previousKey[0] !== STACK_ESTIMATE_QUERY_KEY) return false;
  return typeof safe === "string" && safe !== "" && previousKey[1] === safe;
}
