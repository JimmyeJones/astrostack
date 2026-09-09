/**
 * "Nothing was stacked while you slept, and here is the one switch that changes
 * that" — the offer the walk-away path has been waiting on.
 *
 * **Why this exists.** `Settings.auto_stack` ships **on** (v0.391.0), but only
 * for a *fresh* install: `SettingsStore` re-saves the whole model on every boot,
 * so any box that has ever run carries an explicit `"auto_stack": false` in its
 * `state/config.json`, and no upgrade may overwrite it — a stored value cannot
 * be told apart from a value its owner chose, and flipping one they chose is the
 * breach AGENTS.md §9 exists to prevent. So on every existing install the entire
 * "drop your subs in and come back to a picture" chain sits behind one switch,
 * in Settings, that nothing in the app has ever mentioned. The app knew, every
 * morning, that it had captured a night and made nothing of it, and said
 * nothing.
 *
 * This module is the sentence it should have been saying, and the rules for when
 * saying it would be true. Pure — no React, no fetch — so the *decision* is
 * unit-tested without rendering, which is the pattern every other self-hiding
 * note here follows (`continueTonight.ts`, `rejectionReachNudge.ts`, …).
 *
 * **What it deliberately does not claim.** It promises the *behaviour* ("it will
 * stack each target itself"), never the outcome ("you would have had a
 * picture"). Auto-stack counts **located** (plate-solved) subs, and the night
 * recap this reads counts **kept** ones — kept is always the larger number, so
 * an outcome promise built on it would over-promise on a field ASTAP struggled
 * with. The floor below is used only to keep the offer off a night too thin to
 * be worth one.
 */

/** What the decision needs. Every field is allowed to be missing, because each
 *  arrives from a query that may not have resolved (or from an older backend),
 *  and the honest answer while a fact is unknown is to stay quiet. */
export interface AutoStackNudgeInput {
  /** `Settings.auto_stack`. `undefined` = not loaded yet. */
  autoStack?: boolean;
  /** `Settings.auto_stack_min_frames` — the located-sub floor. */
  minFrames?: number;
  /** Kept subs per target on the night being recapped. */
  targetsKept: number[];
  /** How many pictures the app made inside that window. */
  nNewPictures: number;
}

/** The dismissal signature (see `dismissal.ts`). Constant on purpose: the note
 *  is about a *state*, not about a problem that varies night to night, so "I've
 *  seen this" means seen, not seen-for-Tuesday. It still self-clears when the
 *  switch goes on, because then there is no note at all. */
export const AUTO_STACK_NUDGE_KEY = "astrostack.dashboard.autoStackOffDismissed";
export const AUTO_STACK_NUDGE_SIG = "off";

/** The floor to assume when the setting hasn't loaded — `Settings`' own default,
 *  so the gate is never accidentally 0 (which would offer the nudge on a night
 *  of one sub). */
const DEFAULT_MIN_FRAMES = 3;

/**
 * The sentence to show, or `null` to stay silent.
 *
 * Silent when:
 *  - auto-stack is on, or not known yet — there is nothing to offer, and a note
 *    rendered against an unresolved query would flash on every Dashboard load;
 *  - the app *did* make a picture in the window — something stacked (a manual
 *    run, or a scan under different settings), so "nothing was made" is false
 *    and the note would be a lie told next to its own contradiction;
 *  - no single target kept enough subs to clear the floor — turning the switch
 *    on would not have changed this night either, and an offer that would have
 *    changed nothing is a nag.
 */
export function autoStackNudge(i: AutoStackNudgeInput): string | null {
  if (i.autoStack !== false) return null;
  if (i.nNewPictures > 0) return null;
  const floor = Math.max(1, Math.round(i.minFrames ?? DEFAULT_MIN_FRAMES));
  const best = i.targetsKept.reduce((m, n) => (n > m ? n : m), 0);
  if (best < floor) return null;
  return "Hands-off auto-stack is switched off, so your subs were brought in and "
    + "left as they were. Turn it on and AstroStack will stack each target for "
    + "you as its subs arrive — once enough of them are located and the night "
    + "has gone quiet. You can switch it off again in Settings at any time.";
}

/** The note's heading. It states the *fact* rather than the offer, so a reader
 *  who dismisses it still learns why last night produced nothing. */
export const AUTO_STACK_NUDGE_TITLE = "Your subs came in, but nothing was stacked";

/** The button beside it. Named here so the note and its action are read (and
 *  changed) together, rather than the label living in the component and the
 *  claim living in the sentence. */
export const AUTO_STACK_NUDGE_ACTION = "Turn on auto-stack";

/** What to say once the switch is on, so the click has an answer rather than the
 *  note merely vanishing. Auto-stack acts on the next scan, not instantly, and
 *  the settle window means "quiet night first" — saying so is the difference
 *  between a beginner waiting confidently and a beginner clicking again. */
export const AUTO_STACK_NUDGE_DONE =
  "AstroStack will pick your targets up on its next scan, once each one has "
  + "been quiet for a while. It adds new pictures rather than replacing the "
  + "ones you have, and never writes over an edit you saved.";
