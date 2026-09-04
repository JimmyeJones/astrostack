import type { RejectionOutlook } from "./api/client";

/**
 * "What you just saved won't take a satellite trail out of your overnight
 * stacks" — one clause on the *Save as defaults* confirmation.
 *
 * The gap this closes. Two surfaces already ask the reach question, and neither
 * reaches the moment the decision is made:
 *
 * * `rejectionReachNudge` asks it of the values **on screen**, about the stack
 *   you are about to run by hand. It says nothing about what a *saved* default
 *   will do on every unattended night after this one.
 * * `rejectionOutlookNote` (the Target page) asks it of the **saved** blob, but
 *   is deliberately gated on subs that already carry a flagged trail — so a
 *   mosaic owner whose panels sit at 5 subs has a permanently blind saved
 *   setting and hears about it only on the night a satellite happens to be
 *   caught.
 *
 * Saving *is* the decision, and the Auto toggle is still on screen when the
 * confirmation appears, so this is the one place the answer costs nothing to
 * act on. It is deliberately about the **unattended** path — overnight
 * auto-stacks and one-click *Process target* — rather than the run in front of
 * you, so it complements the form's own caution instead of restating it.
 *
 * Reads the server's answer for the blob that was actually *stored*
 * (`/rejection-outlook` re-resolves it through the same walk-away merge the
 * unattended chain uses), never the live form values.
 *
 * Silent when: there is no answer (older backend, a request that failed,
 * nothing solved yet), the saved settings **do** reach a lone outlier, the
 * method was picked by the chain rather than by the user (that is the app doing
 * its job), or there is no depth to talk about. Advisory only: nothing is
 * changed, and the save itself succeeded.
 *
 * A **drizzled** default used to be excluded too, on the grounds that the memory
 * budget settles its two-pass rejection at run time. That only ever points one
 * way — a pass that is dropped for memory removes even less — and drizzle's clip
 * is the same κ·σ test with the same κ, so a drizzled mosaic saved at panel
 * depth 10 is just as blind. It gets its own clause: Auto outlier removal is
 * overridden while drizzle is on, so "turn it on and save again" would be advice
 * that changes nothing.
 */
export function savedRejectionClause(
  outlook: RejectionOutlook | null | undefined,
): string | null {
  if (!outlook) return null;
  if (outlook.reaches !== false || !outlook.user_chose) return null;

  // The depth the question is really about. On a mosaic no pixel ever sees more
  // than its own panel's subs, so a 20-frame four-panel mosaic is a 5-deep stack
  // as far as a lone trail is concerned.
  const depth = outlook.panel_depth ?? outlook.n_frames ?? 0;
  if (depth <= 0) return null;
  const where = outlook.panel_depth != null
    ? `only about ${depth} sub${depth === 1 ? "" : "s"} land on any one spot of this mosaic`
    : `this target has ${depth} sub${depth === 1 ? "" : "s"}`;

  if (outlook.method === "drizzle") {
    const need = outlook.lone_outlier_min_frames;
    return `Heads-up: overnight and one-click stacks will now drizzle, and ${where}`
      + ` — too few for drizzle's own outlier removal to pick a lone satellite or`
      + ` plane trail out${need ? ` (it needs about ${need})` : ""}. More subs on`
      + ` that part of the sky is the fix; Auto outlier removal can't help while`
      + ` drizzle is on.`;
  }
  if (outlook.method === "sigma-clip") {
    const need = outlook.lone_outlier_min_frames;
    return `Heads-up: overnight and one-click stacks will now use sigma clipping,`
      + ` and ${where} — too few for it to pick a lone satellite or plane trail out`
      + `${need ? ` (it needs about ${need})` : ""}. Turn on Auto outlier removal and`
      + ` save again if you want a method that works at this depth.`;
  }
  // "mean" — a rejection was asked for, but no pass runs at this count at all.
  return `Heads-up: ${where}, so the outlier removal you just saved can't run at all`
    + ` — overnight and one-click stacks will combine as a plain average, leaving any`
    + ` satellite or plane trail in the picture. Auto outlier removal picks a method`
    + ` that works from 3 subs up.`;
}
