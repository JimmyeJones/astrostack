import type { StackRejectionSummary } from "./api/client";

/**
 * One place owns the wording of the "what stacking removed" tint, so the
 * surfaces that show it can't drift into different claims about one picture.
 *
 * (Same reason `fullres.ts` exists: this caption started on the History card and
 * is now also under the full-screen viewer on the Gallery and the Target page,
 * which is where a beginner actually studies their picture.)
 */

/**
 * The caption under a picture whose "what was removed" tint is showing.
 *
 * The overlay alone is a mystery — a beginner sees cyan speckle on their nebula
 * and has no idea whether something went wrong. This names it, and deliberately
 * frames it as protection delivered rather than data thrown away: those samples
 * were in the subs and are *not* in the picture, which is the whole point of
 * stacking many frames. Reuses the run's own measured fraction so it can never
 * disagree with the trust line the History card shows a few pixels above it.
 */
export function removedOverlayCaption(
  rejection: StackRejectionSummary | null | undefined,
): string {
  const lead =
    "The cyan marks are what stacking removed — satellite trails, plane trails " +
    "and cosmic rays that were in your subs but aren’t in your picture.";
  const frac = rejection?.fraction;
  if (typeof frac !== "number" || !Number.isFinite(frac) || frac <= 0) return lead;
  const pct = frac * 100;
  const pctText = pct < 0.1 ? "under 0.1%" : pct < 10 ? `about ${pct.toFixed(1)}%` : `about ${Math.round(pct)}%`;
  return `${lead} That was ${pctText} of your samples; the rest is untouched.`;
}
