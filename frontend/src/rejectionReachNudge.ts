import type { StackEstimate } from "./api/client";

export interface RejectionReachNudge {
  /** The plain-language "here's what will actually happen" sentence. */
  text: string;
  /** The one-click fix, or null when no setting can help at this frame count. */
  fix: { key: "auto_reject"; label: string } | null;
}

/** "The outlier removal you asked for can't remove anything" — a Stack-form
 * caution, decided from the engine's own `rejection_reach` answer.
 *
 * The gap this closes: sigma clipping *dispatches* from 4 frames, but a single
 * satellite trail only stands out enough to clip from `kappa_min_frames` (11 at
 * the default κ=3) — so on every small stack in between it runs, records
 * `REJMODE = sigma-clip`, and clips nothing at all. Below 4 it doesn't even
 * dispatch: the stack silently falls through to a plain average.
 * `seestack.stackhealth` already says so on the finished picture; this is the
 * same fact said while the toggle that would fix it is still on screen.
 *
 * Drizzle has the same gap and is no longer skipped. Its two-pass rejection is
 * the same κ·σ clip with the same κ, so it too reaches nothing until
 * `kappa_min_frames` subs land on a pixel — and a mosaic panel rarely has them.
 * It gets no one-click `fix`: `auto_reject` is overridden while drizzle is on
 * (`_resolve_auto_reject` returns early), so the honest caution here is the
 * sentence, not a button that would change nothing.
 *
 * Silent when: the answer is missing (older backend), the rejection will reach a
 * lone outlier, or the user asked for no rejection at all — this is a "you're
 * not getting the protection you asked for" caution, never a nag at someone who
 * deliberately turned it off. Advisory: nothing changes until the button is
 * pressed.
 */
export function rejectionReachNudge(
  reach: StackEstimate["rejection_reach"] | undefined,
  values: Record<string, unknown>,
): RejectionReachNudge | null {
  if (!reach || reach.reaches) return null;
  // What counts as "you asked for rejection" depends on which pass would run:
  // while drizzle is on the three toggles below it are overridden, and the only
  // rejection that can run is drizzle's own.
  const wanted = reach.method === "drizzle"
    ? !!values.drizzle_reject
    : !!values.sigma_clip || !!values.auto_reject || !!values.min_max_reject;
  if (!wanted) return null;
  const n = reach.n_frames;
  if (n <= 0) return null;
  const subs = `${n} sub${n === 1 ? "" : "s"}`;
  const fix = {
    key: "auto_reject" as const,
    label: "Turn on Auto outlier removal",
  };
  if (reach.method === "drizzle") {
    const need = reach.lone_outlier_min_frames;
    return {
      text: `Drizzle's outlier removal is on, but with ${subs} it can't actually`
        + " drop a passing satellite, plane or cosmic-ray hit — it clips against"
        + " each pixel's own spread, so a lone outlier only stands out far enough"
        + ` to be clipped from about ${need} frames up.`
        + " More subs are the real fix; on a mosaic it is the subs on one panel"
        + " that count, not the total.",
      fix: null,
    };
  }
  if (reach.method === "sigma-clip") {
    const need = reach.lone_outlier_min_frames;
    return {
      text: `Sigma clipping is on, but with ${subs} it can't actually drop a passing`
        + " satellite, plane or cosmic-ray hit — a lone outlier only stands out far"
        + ` enough from the average to be clipped from about ${need} frames up.`
        + " The min/max method removes an extreme from 3 subs up, and Auto outlier"
        + " removal picks it for you at this frame count.",
      fix,
    };
  }
  // Falls through to a plain average: rejection was asked for, but no pass runs.
  if (n >= 3) {
    return {
      text: `This stack will combine as a plain average — with ${subs} the outlier`
        + " removal you picked can't run (sigma clipping needs at least 4 frames),"
        + " so a satellite trail or cosmic-ray hit in any one sub will land in the"
        + " picture. The min/max method works from 3 subs up.",
      fix,
    };
  }
  return {
    text: `With only ${subs}, no outlier removal can run at all — every method needs`
      + " at least 3 frames to tell a satellite trail from the real signal, so"
      + " anything that crossed one sub will show in the result. Reject that frame"
      + " on the Target page, or stack again once you have more subs.",
    fix: null,
  };
}
