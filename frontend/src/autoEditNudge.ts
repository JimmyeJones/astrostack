/**
 * "It stacked your targets overnight and left them as plain stacks" — and the
 * one switch that finishes them.
 *
 * **Why this exists.** `Settings.auto_edit_on_autostack` ships **on**
 * (v0.395.0), and — exactly like `auto_stack` before it (`autoStackNudge.ts`) —
 * only for a *fresh* install: `SettingsStore` re-saves the whole model on every
 * boot, so any box that has ever run carries an explicit
 * `"auto_edit_on_autostack": false` in `state/config.json` that no upgrade may
 * overwrite (§9 — a stored value cannot be told apart from a value its owner
 * chose). So on an established install the walk-away chain now stacks by itself
 * and then stops, one step short of the picture: the owner comes back to a
 * linear master, which is the flat, dark combine before any stretch or colour,
 * and has to open each one in the editor and press Auto. `AutoStackOffNote`
 * closed the first half of that gap; nothing in the app has ever mentioned the
 * second, and the setting sits on a Settings tab behind an "Auto-stack" switch.
 *
 * This module is the sentence it should be saying, and the rules for when
 * saying it is *true*. Pure — no React, no fetch — so the decision is
 * unit-tested without rendering, the pattern every self-hiding note here
 * follows (`autoStackNudge.ts`, `continueTonight.ts`, `rejectionReachNudge.ts`).
 *
 * **What it deliberately does not claim.** It promises the *behaviour* ("it
 * will finish each new picture the way Auto does"), never that the result will
 * be better than what the owner would do by hand — and it never says a picture
 * is *missing*, because it is not: the stack is there, it is simply unfinished.
 * It also reads the scan's own tallies rather than inferring from the pictures
 * list, so a target finished by its own per-target preference is counted as
 * finished (`webapp/auto_edit_pref`) instead of being blamed on the switch.
 */

/** What the decision needs. Every field may be missing, because each arrives
 *  from a query that may not have resolved (or from a backend too old to send
 *  it), and the honest answer while a fact is unknown is to stay quiet. */
export interface AutoEditNudgeInput {
  /** `Settings.auto_edit_on_autostack`. `undefined` = not loaded yet. */
  autoEditOnAutostack?: boolean;
  /** Targets the newest hands-off scan stacked by itself. */
  autoStacked?: number;
  /** How many of those it went on to finish into a picture. */
  autoEdited?: number;
}

/** The dismissal signature (see `dismissal.ts`). Constant on purpose, like
 *  `AUTO_STACK_NUDGE_SIG`: the note is about a *state*, not about a problem
 *  that varies night to night, so "I've seen this" means seen — not
 *  seen-for-Tuesday. It still self-clears when the switch goes on, because then
 *  there is no note at all. */
export const AUTO_EDIT_NUDGE_KEY = "astrostack.dashboard.autoEditOffDismissed";
export const AUTO_EDIT_NUDGE_SIG = "off";

/** A tally as a whole, non-negative count. The numbers come off a job record
 *  the app wrote — possibly months and several versions ago — so a missing,
 *  fractional or non-finite value has to read as "nothing to say" rather than
 *  reach a sentence, the same tolerance `overnight._count` applies server-side. */
function count(value: number | undefined): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return 0;
  return Math.max(0, Math.trunc(value));
}

/**
 * The sentence to show, or `null` to stay silent.
 *
 * Silent when:
 *  - auto-editing is on, or not known yet — there is nothing to offer, and a
 *    note rendered against an unresolved query would flash on every load;
 *  - the newest hands-off scan stacked nothing by itself — with auto-stack off
 *    (or a night it held everything back) this switch would have changed
 *    nothing, and `AutoStackOffNote` is the note that fits that install;
 *  - it finished everything it stacked — some other route is already doing the
 *    job (a per-target preference), so the claim would be false.
 */
export function autoEditNudge(i: AutoEditNudgeInput): string | null {
  if (i.autoEditOnAutostack !== false) return null;
  const left = count(i.autoStacked) - count(i.autoEdited);
  if (left <= 0) return null;
  const what = left === 1
    ? "stacked one of your targets by itself and left its picture unfinished"
    : `stacked ${left} of your targets by itself and left their pictures unfinished`;
  const them = left === 1 ? "It is the plain stack" : "They are plain stacks";
  const they = left === 1 ? "it" : "they";
  return `AstroStack ${what}. ${them} — the raw combine, before`
    + ` any stretch, colour or clean-up, which is why ${they} can look flat and`
    + " dark. Turn on auto-editing and it will finish each new picture the same"
    + " way the editor's Auto-process button does, as soon as it has stacked it."
    + " An edit you saved yourself is never written over.";
}

/** The note's heading. It states the *fact* rather than the offer, so a reader
 *  who dismisses it still learns why last night's pictures look flat. */
export const AUTO_EDIT_NUDGE_TITLE = "Your pictures were stacked, but not finished";

/** The button beside it. Named here so the note and its action are read (and
 *  changed) together, rather than the label living in the component and the
 *  claim living in the sentence. */
export const AUTO_EDIT_NUDGE_ACTION = "Turn on auto-editing";

/** What to say once the switch is on, so the click has an answer rather than
 *  the note merely vanishing. Auto-editing acts on the *next* stack, not on the
 *  pictures already made — saying so is the difference between a beginner
 *  waiting confidently and a beginner clicking again — and the two ways back
 *  out are named here rather than left to be discovered. */
export const AUTO_EDIT_NUDGE_DONE =
  "AstroStack will finish each new picture as it stacks it, from the next scan "
  + "on. The pictures you already have are untouched — open one and press "
  + "Auto-process to finish it now. Every finished picture is one Reset from "
  + "the plain stack, and the link under it leaves that one target alone.";
