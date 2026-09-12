// "Shoot these before they're gone" — the pure wording behind the card that
// names the targets whose observing season is ending.
//
// Kept out of the component, like `planweek.ts` and `tonight.ts`, so the claims
// it makes ("about three weeks left on M 42") are testable without a DOM.

import type { ClosingTarget, SeasonClosing } from "./api/client";
import { formatIntegration } from "./format";

/**
 * "this is its last week" / "about a week left" / "about 5 weeks left".
 *
 * Weeks, not days: the scan samples one night a week, so a day count would be
 * precision the measurement does not have. The wording is deliberately hedged
 * for the same reason — the true last night is somewhere in the week *after*
 * the one reported, so "about" is the honest word and never an apology.
 */
export function weeksLeftPhrase(weeks: number): string {
  const w = Math.max(0, Math.round(weeks));
  if (w === 0) return "this is its last week";
  if (w === 1) return "about a week left";
  return `about ${w} weeks left`;
}

/** The date of the last night it is worth shooting, as a short local label
 * ("3 Mar"). Falls back to the raw value if it can't be parsed, so a surprising
 * string is shown rather than swallowed. */
export function lastNightLabel(date: string): string {
  // Parsed at local noon so a timezone offset can never roll the evening's own
  // calendar date onto the neighbouring day — the same care `planweek.ts` takes.
  const d = new Date(`${date}T12:00:00`);
  if (Number.isNaN(d.getTime())) return date;
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

/**
 * One target's line: how long is left, and what you already have on it.
 *
 * The second half is what turns a countdown into a decision. "About two weeks
 * left" alone does not say whether to bother; "about two weeks left · you have
 * 22 min on it" does — and a target already 10 h deep reads, correctly, as one
 * that can be let go.
 */
export function closingTargetLine(t: ClosingTarget): string {
  const left = weeksLeftPhrase(t.weeks_left);
  const have = t.total_exposure_s > 0
    ? `you have ${formatIntegration(t.total_exposure_s)} on it`
    : "you haven't kept any of it yet";
  return `${left} · ${have} · last good night around ${lastNightLabel(t.last_night)}`;
}

/**
 * The card's one-sentence headline, or `null` when there is nothing to say.
 *
 * `null` is the ordinary answer and the card renders nothing for it: most of
 * the year nothing of yours is leaving, and a planning card that speaks anyway
 * is the "one more always-on banner" the owner's standing complaint is about.
 */
export function closingHeadline(plan: SeasonClosing | null | undefined): string | null {
  const rows = plan?.targets ?? [];
  if (rows.length === 0) return null;
  const soonest = rows[0];
  if (rows.length === 1) {
    return `${soonest.name} is on its way out of your sky — ${weeksLeftPhrase(soonest.weeks_left)}.`;
  }
  return `${rows.length} of your targets are on their way out of your sky — `
    + `${soonest.name} first, ${weeksLeftPhrase(soonest.weeks_left)}.`;
}

/** The line under the headline: why this is worth acting on rather than noting.
 *
 * Says the consequence in the owner's own units — a season, not a number of
 * degrees — because "it drops below 30° during darkness" is the mechanism and
 * "you won't get another go until next year" is the reason to care. */
export const CLOSING_WHY =
  "Once a target sets during your dark hours it's gone until the same season "
  + "next year. A clear night spent on one of these buys something the rest of "
  + "the year can't.";

/**
 * Weeks left at or below which a target is *urgent* rather than merely noted.
 *
 * The Tonight card can afford to list a target with five weeks left, because
 * somebody opening a planning page is planning. The Dashboard cannot: a note
 * there is shown to somebody who came to look at their pictures, and spending
 * that slot on something a month away is how a self-hiding note becomes a
 * banner. One week or less is the bar, because that is the case where waiting
 * for the next clear night is itself the mistake.
 *
 * One constant for both surfaces — the card's "Last chance" badge and the
 * Dashboard note — so the two can never disagree about which targets are the
 * urgent ones.
 */
export const CLOSING_URGENT_WEEKS = 1;

/** The rows urgent enough to interrupt somebody with, soonest first (the
 * endpoint already orders them). Empty — say nothing — is the usual answer. */
export function urgentlyClosing(
  plan: SeasonClosing | null | undefined,
): ClosingTarget[] {
  return (plan?.targets ?? []).filter((t) => t.weeks_left <= CLOSING_URGENT_WEEKS);
}

/**
 * The Dashboard note's one sentence, or `null` when nothing is that urgent.
 *
 * Deliberately shorter than the card's: this is a pointer, not the answer. It
 * names the target (and how many others are in the same week) and leaves the
 * detail — how much you have, which night is the last one — to the page that
 * exists for planning.
 */
export function closingUrgentSentence(
  plan: SeasonClosing | null | undefined,
): string | null {
  const rows = urgentlyClosing(plan);
  if (rows.length === 0) return null;
  const first = rows[0];
  const lead = first.weeks_left <= 0
    ? `This is your last week for ${first.name}`
    : `${first.name} has about a week of good nights left`;
  if (rows.length === 1) return `${lead} — after that it's gone until next year.`;
  const others = rows.length - 1;
  return `${lead}, and ${others} other target${others === 1 ? "" : "s"} of yours `
    + `${others === 1 ? "is" : "are"} in the same week — after that they're gone `
    + "until next year.";
}
