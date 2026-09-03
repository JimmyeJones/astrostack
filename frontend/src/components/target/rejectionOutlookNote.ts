import type { RejectionOutlook } from "../../api/client";

export interface RejectionOutlookNoteText {
  title: string;
  /** The plain-language "here's what will actually happen" paragraph. */
  text: string;
}

/**
 * "The outlier removal this target is saved with won't reach these trails."
 *
 * The gap this closes. The Stack form already warns when the values *on screen*
 * can't drop a lone satellite trail, and "How's my stack?" says it afterwards,
 * on a picture that already has the trail baked in. Neither reaches the path a
 * walk-away owner actually uses: the overnight auto-stack and the one-click
 * **Process target** button both stack with the target's *saved* settings, and
 * the chain only picks a method when the user picked none. So an owner who once
 * saved sigma clipping gets it on every unattended stack, silently reaching
 * nothing on any night — or any mosaic panel — thinner than about 11 subs.
 *
 * Gated hard, because this is the page the owner already calls busy:
 *
 * * Only when subs on this target **actually carry a trail** (`streaked`). The
 *   warning is about damage that is provably present, not a standing lecture
 *   about a setting.
 * * Only when the setting is the **user's own** (`user_chose`). When the chain
 *   picked the method, it picked one that works — that is the app doing its job,
 *   and saying so would be noise.
 * * Only when it genuinely **cannot reach** (`reaches === false`). A deep enough
 *   stack, a missing verdict (nothing solved yet), an older backend with no such
 *   endpoint, or a drizzled run (whose own two-pass rejection is settled by the
 *   memory budget at run time, which this cannot know) all render nothing.
 *
 * Advisory only: it never changes a setting, and the fix it points at is the
 * Stack form the user was always free to visit.
 */
export function rejectionOutlookNote(
  outlook: RejectionOutlook | null | undefined,
  streaked: number,
): RejectionOutlookNoteText | null {
  if (!outlook || streaked <= 0) return null;
  if (outlook.reaches !== false || !outlook.user_chose) return null;
  if (outlook.method === "drizzle") return null;

  const subs = streaked === 1 ? "1 sub here carries" : `${streaked} subs here carry`;
  // The depth the question is really about. On a mosaic no pixel ever sees more
  // than its own panel's subs, so a 20-frame four-panel mosaic is a 5-deep
  // stack as far as a lone trail is concerned.
  const depth = outlook.panel_depth ?? outlook.n_frames ?? 0;
  const need = outlook.lone_outlier_min_frames;
  const where = outlook.panel_depth != null
    ? `only about ${depth} land on any one spot of this mosaic`
    : `there are ${depth}`;

  if (outlook.method === "sigma-clip") {
    return {
      title: "Your saved outlier removal won't take these trails out",
      text:
        `${subs} a satellite or plane trail, and this target is saved to`
        + ` stack with sigma clipping — but ${where}, and sigma clipping can't pick a`
        + ` lone trail out of that few${need ? ` (it needs about ${need})` : ""}.`
        + " Stacking now, by hand or overnight, leaves the trail in the picture."
        + " Auto outlier removal picks a method that works at your stack's depth.",
    };
  }
  // "mean" — a rejection was asked for, but no pass runs at this count at all.
  return {
    title: "Nothing will remove these trails from your next stack",
    text:
      `${subs} a satellite or plane trail, and with ${where} the outlier`
      + " removal this target is saved with can't run at all — the stack combines as"
      + " a plain average, so the trail lands in the picture. Auto outlier removal"
      + " picks a method that works from 3 subs up.",
  };
}
