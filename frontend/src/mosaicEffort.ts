// "A 3×2 mosaic — can I do that tonight?"
//
// The planner already answers *how many panels* an oversized target needs (the
// "Needs 3×2 mosaic" badge, from `seestack.framing.mosaic_plan`). But the panel
// count is not the decision a beginner is making: 6 panels is a very different
// evening from 12, and nothing on the screen where they choose what to point at
// says which. This turns the panel count into the figure they are actually
// weighing — *about how many clear nights* — using the owner's own measured pace
// rather than a guess.
//
// Pure and I/O-free, so every silence can be pinned in isolation. It is a
// *clause*, not a card: the caller appends it to the framing badge's existing
// tooltip, so nothing new is added to an already-dense screen.

import type { MosaicPlan } from "./api/client";
import { clearNightsFromPace, nightWord } from "./components/clearNights";
import { formatIntegration } from "./format";
import { goalHoursForType } from "./readiness";

/**
 * How long a mosaic of this object would take, in the owner's own clear nights.
 *
 * `panels × the per-type goal` is the honest total: the per-object-type goal is
 * a *depth* ("enough for a clean image") and every panel has to reach it, so a
 * 6-panel nebula at 4 h a field is 24 h of shooting. Panel overlap does not
 * reduce that — the overlapped strips simply end up deeper than the edges — so
 * the panel count, not the mosaic's field-fulls of sky, is the right multiplier
 * for a question about *time*. (`integrationReadiness` scales by field-fulls
 * instead, because it is asking a different question: how deep is the picture I
 * already have.)
 *
 * `usualPaceSeconds` is the library-wide typical clear-night output served by
 * the planner (`usual_pace_s`), i.e. the median of the per-target paces the
 * "~1 more clear night finishes this" row already divides by.
 *
 * The sentence prices the *whole* grid from scratch, which is honest because the
 * framing badge it rides on is only ever attached to a target the owner has not
 * started: the planner fills `framing`/`mosaic` on the catalog branch alone
 * (`seestack.nightplan.plan_tonight`), never on an already-targeted row.
 *
 * Returns null — say nothing rather than guess — when there is no mosaic plan,
 * when the owner has no measured pace at all (the first-timer this must never
 * lecture), or when the arithmetic has nothing to give. So an install that has
 * never finished a night sees exactly the badge it sees today.
 */
export function mosaicEffortText(
  mosaic: MosaicPlan | null | undefined,
  type: string | null | undefined,
  usualPaceSeconds?: number | null,
): string | null {
  if (!mosaic || !Number.isFinite(mosaic.panels) || mosaic.panels < 2) return null;
  const totalSeconds = mosaic.panels * goalHoursForType(type) * 3600;
  const est = clearNightsFromPace(totalSeconds, usualPaceSeconds);
  if (!est || est.nights === null) return null;
  // The assumption is stated, not hidden: the number only means anything if you
  // know it is costing every panel the depth a single field would get. Saying so
  // is what keeps this from being an invented per-panel constant.
  return (
    `At your usual pace (~${formatIntegration(est.paceSeconds)} of kept subs per ` +
    `clear night), giving all ${mosaic.panels} panels the depth you'd give one ` +
    `field is about ${est.nights} clear ${nightWord(est.nights)} of shooting.`
  );
}

/**
 * Append the effort clause to a framing badge's hover, or hand the badge back
 * untouched when there is nothing to say.
 *
 * Lives here rather than inside `framingRowBadge` for two reasons: the goal
 * table it needs is in `readiness.ts`, which imports the object-type buckets
 * *from* `tonight.ts` (folding the clause in there would close an import cycle);
 * and both planner surfaces that show the badge — the Tonight table and the
 * Dashboard's "Try something new tonight" card — then compose the sentence the
 * same way, in one place, instead of each writing their own.
 */
export function withMosaicEffort(
  badge: { label: string; color: string; tooltip: string } | null,
  mosaic: MosaicPlan | null | undefined,
  type: string | null | undefined,
  usualPaceSeconds?: number | null,
): { label: string; color: string; tooltip: string } | null {
  if (!badge) return null;
  const effort = mosaicEffortText(mosaic, type, usualPaceSeconds);
  return effort ? { ...badge, tooltip: `${badge.tooltip} ${effort}` } : badge;
}
