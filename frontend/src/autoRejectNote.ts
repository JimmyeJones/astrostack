import type { StackEstimate } from "./api/client";

/**
 * What "Auto outlier removal" will actually do, in plain words.
 *
 * The toggles it overrides are greyed out on the form, so this is the only place
 * that says *which* method is going to run and where the boundary sits — the
 * alternative being to discover it in History after the stack.
 *
 * **On a mosaic the number that decides is not the frame count.** Every
 * threshold in this decision is a statement about how many samples land on one
 * pixel, and on a mosaic that is a panel's depth: 21 subs shot as four panels
 * overlap perhaps 3 deep, so the engine picks min/max where the count alone
 * would have said sigma clipping. The backend resolves the method through the
 * engine's own picker and reports the depth beside it; this wording follows —
 * it says "on one spot" rather than "subs" whenever a depth is given, because a
 * sentence that quotes 21 subs and then names the method for 3 reads as a bug.
 *
 * Pure and null-safe: `null` whenever there is nothing to say (Auto is off,
 * drizzle keeps its own pass, or nothing solved yet).
 */
export function autoRejectMethodNote(
  resolved: StackEstimate["auto_reject_resolved"] | undefined,
): string | null {
  if (!resolved || resolved.n_frames <= 0) return null;
  const { method, n_frames: n, switch_at_frames: switchAt } = resolved;
  const depth = resolved.panel_depth ?? null;
  // A depth only says something the count doesn't when it is genuinely smaller;
  // a single field reports null, and a mosaic whose panels all overlap fully
  // would be quoting the same number twice.
  const byDepth = depth !== null && depth > 0 && depth < n;

  if (byDepth) {
    const lead = `Auto outlier removal is on, so it picks the method from how many subs land on each pixel: your ${n} subs are spread across a mosaic that is only ${depth} deep where it is thinnest`;
    return method === "min_max"
      ? `${lead}, so it will use min/max rejection, which drops the highest and lowest value at each pixel. It switches to sigma clipping once about ${switchAt} subs overlap on one spot, where there are enough samples to measure each pixel's spread.`
      : `${lead}, and that is enough for sigma clipping, which rejects pixels that sit far from the average. Below about ${switchAt} subs on one spot it uses min/max rejection instead.`;
  }
  return method === "min_max"
    ? `Auto outlier removal is on, so it picks the method from your frame count: with ${n} accepted, solved sub${n === 1 ? "" : "s"} it will use min/max rejection, which drops the highest and lowest value at each pixel. It switches to sigma clipping from about ${switchAt} subs, where there are enough frames to measure each pixel's spread.`
    : `Auto outlier removal is on, so it picks the method from your frame count: with ${n} accepted, solved subs it will use sigma clipping, which rejects pixels that sit far from the average. Below about ${switchAt} subs it uses min/max rejection instead.`;
}
