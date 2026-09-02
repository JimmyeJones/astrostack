// "Plan my week" — the pure arithmetic and wording behind the card that says
// which of your own targets to point at, on which of the next few nights.
//
// Kept out of the component so the claims it makes ("Thursday is your best M 31
// night") are testable without a DOM, exactly as `tonight.ts` is.

import type { PlanWeek, TargetBestNight, WeekNight } from "./api/client";

// A night's own local date, as the backend labels it: the calendar date of the
// *evening* the darkness belongs to. Parsed at local noon so a timezone offset
// can never roll it onto the neighbouring day.
function nightDate(date: string): Date | null {
  const d = new Date(`${date}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

// Whole days from `now`'s calendar date to `date`'s, ignoring clock time — so
// "tonight" stays tonight at 23:00 and at 00:30 the night is still labelled by
// the evening it started on.
function daysAhead(date: string, now: Date): number | null {
  const d = nightDate(date);
  if (d === null) return null;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0, 0);
  return Math.round((d.getTime() - today.getTime()) / 86_400_000);
}

/**
 * How to name one of the nights ahead: "Tonight", "Tomorrow", then the weekday
 * ("Thursday") while it is still this coming week, and a dated label
 * ("Thu 11 Sep") once a bare weekday would be ambiguous.
 *
 * A user in the small hours is still *inside* last evening's night, so a date
 * one day behind reads "Tonight" rather than a stale weekday.
 */
export function weekNightLabel(date: string, now: Date): string {
  const d = nightDate(date);
  if (d === null) return date;
  const ahead = daysAhead(date, now);
  if (ahead === null) return date;
  if (ahead <= 0) return "Tonight";
  if (ahead === 1) return "Tomorrow";
  if (ahead <= 6) return d.toLocaleDateString([], { weekday: "long" });
  return d.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}

/** The same label, lower-cased for mid-sentence use ("your best night is Thursday"). */
export function weekNightLabelInline(date: string, now: Date): string {
  const label = weekNightLabel(date, now);
  return label === "Tonight" || label === "Tomorrow" ? label.toLowerCase() : label;
}

/**
 * The single best night in the range — the highest-scoring nightly pick.
 *
 * Ties break towards the *sooner* night: given two equally good nights a
 * beginner should go out on the first one, not wait for the second.
 */
export function bestNightOfWeek(nights: WeekNight[]): WeekNight | null {
  let best: WeekNight | null = null;
  for (const n of nights) {
    if (n.best === null) continue;
    if (best === null || n.best.score > (best.best?.score ?? -Infinity)) best = n;
  }
  return best;
}

/**
 * The card's one-sentence headline, or `null` when there is nothing honest to
 * say (no location, no positioned targets, nothing well placed all week).
 *
 * Deliberately names a target and a night, because that is the whole question:
 * "Your best night this week is Thursday — M 31, 4.1 h above 30°."
 */
export function weekHeadline(plan: PlanWeek, now: Date): string | null {
  const night = bestNightOfWeek(plan.nights);
  if (night === null || night.best === null) return null;
  const hours = night.best.minutes_above_min_alt / 60;
  const span = hours >= 1
    ? `${hours.toFixed(1)} h`
    : `${Math.round(night.best.minutes_above_min_alt)} min`;
  return `Your best night is ${weekNightLabelInline(night.date, now)}`
    + ` — ${night.best.name}, ${span} above ${Math.round(plan.min_altitude_deg)}°.`;
}

/**
 * Why the card has nothing to show, in the user's own terms — or `null` when it
 * does have something. Each branch names the fix, so the empty state is a next
 * step rather than a shrug.
 */
export function weekEmptyReason(plan: PlanWeek): string | null {
  if (plan.nights.some((n) => n.best !== null)) return null;
  if (plan.location_source === "none") {
    return "Set your observing location and this will say which night to go out on.";
  }
  if (plan.n_targets_with_position === 0) {
    return "None of your targets have a known position yet — plate-solve some subs "
      + "and this will plan them.";
  }
  if (plan.nights.length === 0) {
    return "There's no real darkness at your location over the next few nights.";
  }
  return `Nothing you've started gets above ${Math.round(plan.min_altitude_deg)}° for long `
    + "enough over the next few nights — lowering the minimum altitude will widen it.";
}

/**
 * Each target's own best night, soonest first — "M 31 Thursday, M 42 Saturday".
 *
 * Drops the target the headline already named on that night, so the follow-up
 * line adds something instead of repeating it, and returns at most `limit` so a
 * forty-target library doesn't become a wall.
 */
export function otherTargetNights(
  plan: PlanWeek, limit = 4,
): TargetBestNight[] {
  const headline = bestNightOfWeek(plan.nights);
  const named = headline?.best?.safe;
  const namedDate = headline?.date;
  return plan.targets
    .filter((t) => !(t.safe === named && t.date === namedDate))
    .slice(0, limit);
}

/** "M 31 — Thursday" for one of those rows. */
export function targetNightPhrase(t: TargetBestNight, now: Date): string {
  return `${t.name} — ${weekNightLabel(t.date, now)}`;
}

/**
 * A Moon caution for a night, or `null` when the Moon isn't a problem.
 *
 * Uses illumination *and* how much of the usable window the Moon is actually up:
 * a full Moon that stays below the horizon all night is no problem, and saying
 * otherwise would send a beginner indoors on a perfectly good night.
 */
export function weekMoonNote(night: WeekNight): string | null {
  const up = night.best?.moon_up_fraction;
  if (up === null || up === undefined || up <= 0.1) return null;
  if (night.moon_illumination < 0.4) return null;
  const pct = Math.round(night.moon_illumination * 100);
  return up >= 0.9 ? `Moon ${pct}%, up all night` : `Moon ${pct}%, up part of the night`;
}
