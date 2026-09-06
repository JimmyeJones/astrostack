import type { StackEstimate } from "./api/client";

export interface StreakRejectionAdvice {
  /** The plain-language sentence. */
  text: string;
  /** The one-click fix, or null when no setting can take the trail out here. */
  fix: { key: "auto_reject" | "drizzle_reject"; label: string } | null;
}

/** "You kept the streaked frames and switched outlier removal off" — the Stack
 * form's caution for the one case `rejectionReachNudge` deliberately stays quiet
 * about.
 *
 * The two are complementary halves of one question, and both now read the
 * engine's own `rejection_reach` rather than a hand-written copy of the
 * dispatcher's gates. `rejectionReachNudge` answers *"you asked for rejection —
 * will it reach?"*; this answers *"you asked for none — should you?"*, and, when
 * the sub count is below every method's floor, that no setting on the form can
 * help so the honest move is to drop those frames or shoot more.
 *
 * The hand-written predicate this replaced (`(auto && n>=3) || (sigma && n>=4)
 * || (minmax && n>=3)`) spelled out the *dispatch* gates, so on a 1–2 sub stack
 * with sigma clipping on — the shipped default — it read as "no per-pixel
 * rejection enabled" and offered a button to turn on the setting that was
 * already on and could not have worked, beside a `rejectionReachNudge` saying
 * the opposite. Deciding both from one engine answer makes that contradiction
 * unrepresentable.
 *
 * Silent when: no accepted, solved frame carries a streak; the estimate hasn't
 * answered yet (or an older backend doesn't carry `best_available`); or the user
 * *did* ask for rejection — that is the sibling nudge's case, whether it reaches
 * or not, so the two can never stack a second alert on the same stack.
 */
export function streakRejectionAdvice(args: {
  streaked: number;
  reach: StackEstimate["rejection_reach"] | undefined | null;
  values: Record<string, unknown>;
}): StreakRejectionAdvice | null {
  const { streaked, reach, values } = args;
  if (streaked <= 0 || !reach) return null;
  const best = reach.best_available;
  if (!best) return null;
  const drizzle = !!values.drizzle;
  // Which toggles are live depends on the path: with drizzle on, the three
  // below it are overridden and only drizzle's own two-pass rejection can run.
  // Same split as `rejectionReachNudge`, deliberately — a frame is either its
  // case or this one, never both.
  const wanted = drizzle
    ? !!values.drizzle_reject
    : !!values.sigma_clip || !!values.auto_reject || !!values.min_max_reject;
  if (wanted) return null;

  const trails = streaked === 1 ? "the trail" : "the trails";
  const them = streaked === 1 ? "it" : "them";
  const carry = `${streaked} accepted frame${streaked === 1 ? " has" : "s have"}`
    + " a detected satellite/plane streak, but this stack has no per-pixel"
    + ` outlier removal turned on — ${trails} will show in the result.`;

  if (best.reaches) {
    return {
      text: drizzle
        ? `${carry} Turn on drizzle outlier rejection to take ${them} out while`
          + " keeping the frames."
        : `${carry} Turn on Auto outlier removal to take ${them} out while`
          + " keeping the frames — it picks a method that works at your stack's"
          + " depth.",
      fix: drizzle
        ? { key: "drizzle_reject", label: "Turn on drizzle outlier rejection" }
        : { key: "auto_reject", label: "Turn on Auto outlier removal" },
    };
  }

  // Below every floor there is no setting to offer, so offer none: a button
  // that swaps no rejection for no rejection is worse than the sentence alone.
  const need = best.lone_outlier_min_frames;
  const floor = need != null
    ? ` Outlier removal needs about ${need} sub${need === 1 ? "" : "s"} on the`
      + " same spot of sky before it can tell a trail from the real signal, and"
      + " this stack is thinner than that."
    : " No outlier-removal setting can run on this stack.";
  return {
    text: `${carry}${floor} Reject those frames on the Target page, or stack`
      + " again once you have more subs.",
    fix: null,
  };
}
