import type { LifeListCounts } from "../api/client";

/** Pure phrasing for the Dashboard's life-list nudge: "you've got 42 of the 110".
 *
 * The life list is already a page (`/life-list`); what it lacked was a reason to
 * open it. The Messier count is the whole hook — a finite, famous, countable set
 * — and the Dashboard is the one screen a beginner sees every session. This file
 * only decides the *words*; the counts come from the same
 * `seestack.lifelist.life_list_summary` the life-list page's own header uses, so
 * the two can never quote different numbers. No React, no I/O.
 */

/** How many of the 110 you'd want a nudge about; below this the milestone
 *  language ("you're over halfway") would be a lie, so it simply isn't used. */
const HALFWAY = 0.5;

/** Within this many objects of the whole list, the remaining count is the more
 *  motivating half of the sentence ("just 4 to go" beats "106 of 110"). */
export const HOME_STRAIGHT_REMAINING = 10;

/**
 * The one-line read-out, or `""` when there is nothing worth saying.
 *
 * Silent at **zero captured**, deliberately: a fresh install has enough on
 * screen telling it what to do first, and "0 of 110" is a scoreboard for a game
 * that hasn't started. It is also silent on a nonsense or absent tally rather
 * than printing a placeholder into the one line a beginner reads every session.
 *
 * The tail changes with how far along you are, because the motivating fact
 * does: near the end it is what's **left**, in the middle it is that you're
 * past halfway, and early on the plain count says enough on its own.
 */
export function lifeListLine(counts: LifeListCounts | null | undefined): string {
  const got = counts?.messier_captured;
  const total = counts?.messier_total;
  if (!Number.isFinite(got as number) || !Number.isFinite(total as number)) return "";
  const captured = got as number;
  const all = total as number;
  if (captured <= 0 || all <= 0 || captured > all) return "";

  const head = `You've photographed ${captured} of the ${all} Messier objects`;
  const left = all - captured;
  if (left === 0) return `${head} — the whole list. Every single one.`;
  if (left <= HOME_STRAIGHT_REMAINING) {
    return `${head} — just ${left === 1 ? "one" : left} to go.`;
  }
  if (captured / all >= HALFWAY) return `${head} — over halfway.`;
  return `${head}.`;
}
