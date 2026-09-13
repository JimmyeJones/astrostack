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
import { fmtGoal, goalHoursForType, type GoalDifficulty } from "./readiness";

/**
 * The two figures behind "how big a job is that mosaic, then?", or null when
 * there is nothing honest to say.
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
 * Split out of :func:`mosaicEffortText` because the panel count reaches a
 * beginner on **three** surfaces and only one of them has a pace to spend it in.
 * The planner's framing badge can say "about 5 clear nights"; the Target page's
 * *measured* framing verdict and the identity card's catalogue line are on
 * library screens that never fetch `usual_pace_s`, so before this they stopped
 * at "About a 3×3 mosaic (9 panels) covers all of it" — a panel count, where the
 * decision is a time commitment. Sharing the arithmetic is what stops the three
 * of them pricing one grid three ways.
 *
 * Returns null — say nothing rather than guess — when there is no mosaic plan or
 * the grid is not actually a grid (fewer than 2 panels).
 */
export function mosaicDepthHours(
  mosaic: MosaicPlan | null | undefined,
  type: string | null | undefined,
  difficulty?: GoalDifficulty,
): { panels: number; perFieldHours: number; totalHours: number } | null {
  if (!mosaic || !Number.isFinite(mosaic.panels) || mosaic.panels < 2) return null;
  const perFieldHours = goalHoursForType(type, difficulty);
  if (!Number.isFinite(perFieldHours) || perFieldHours <= 0) return null;
  return {
    panels: mosaic.panels,
    perFieldHours,
    totalHours: mosaic.panels * perFieldHours,
  };
}

/**
 * The same answer in hours, for the surfaces that have no pace to divide by.
 *
 * Deliberately the *same clause* as :func:`mosaicEffortText` — "giving all N
 * panels the depth you'd give one field" — so a reader who has seen the
 * planner's sentence recognises this one as the same claim rather than a second
 * opinion, and so the assumption stays stated rather than hidden. The per-field
 * figure is printed too, because it is the number the readiness card two inches
 * up the Target page is already showing as this object's goal: on a single field
 * `integrationReadiness`'s `baseGoalHours` *is* `goalHoursForType`, and both go
 * through `fmtGoal`, so the two cannot print one goal two ways.
 *
 * This prices the whole grid from scratch even on a target the owner has already
 * started, which is the honest reading of the question it answers: the panel
 * grid is a *new* way to shoot the object, and the subs already on one pointing
 * are a few minutes against a figure in hours. Being about "next session" rather
 * than "what's left", it deliberately does not try to subtract them.
 */
export function mosaicDepthText(
  mosaic: MosaicPlan | null | undefined,
  type: string | null | undefined,
  difficulty?: GoalDifficulty,
): string | null {
  const d = mosaicDepthHours(mosaic, type, difficulty);
  if (!d) return null;
  return (
    `Giving all ${d.panels} panels the depth you'd give one field ` +
    `(~${fmtGoal(d.perFieldHours)} h each) is about ` +
    `${fmtGoal(d.totalHours)} h of shooting.`
  );
}

/**
 * How long a mosaic of this object would take, in the owner's own clear nights.
 *
 * The total comes from :func:`mosaicDepthHours` — `panels × the per-type goal`,
 * and see there for why the panel count rather than the field-fulls is the right
 * multiplier for a question about time. This is that total spent at a pace.
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
  difficulty?: GoalDifficulty,
): string | null {
  const depth = mosaicDepthHours(mosaic, type, difficulty);
  if (!depth) return null;
  const est = clearNightsFromPace(depth.totalHours * 3600, usualPaceSeconds);
  if (!est || est.nights === null) return null;
  // The assumption is stated, not hidden: the number only means anything if you
  // know it is costing every panel the depth a single field would get. Saying so
  // is what keeps this from being an invented per-panel constant.
  return (
    `At your usual pace (~${formatIntegration(est.paceSeconds)} of kept subs per ` +
    `clear night), giving all ${depth.panels} panels the depth you'd give one ` +
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
  difficulty?: GoalDifficulty,
): { label: string; color: string; tooltip: string } | null {
  if (!badge) return null;
  const effort = mosaicEffortText(mosaic, type, usualPaceSeconds, difficulty);
  return effort ? { ...badge, tooltip: `${badge.tooltip} ${effort}` } : badge;
}
