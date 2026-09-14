// "Plan my week" — the pure arithmetic and wording behind the card that says
// which of your own targets to point at, on which of the next few nights.
//
// Kept out of the component so the claims it makes ("Thursday is your best M 31
// night") are testable without a DOM, exactly as `tonight.ts` is.

import type {
  ClosingTarget, PlanWeek, SeasonClosing, TargetBestNight, WeekNight,
} from "./api/client";
import { weeksLeftPhrase } from "./closingSeason";
import { formatMinutes } from "./tonight";

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
  plan: PlanWeek, limit = 4, closing?: SeasonClosing | null,
): TargetBestNight[] {
  const headline = bestNightOfWeek(plan.nights);
  const named = headline?.best?.safe;
  const namedDate = headline?.date;
  const rows = plan.targets
    .filter((t) => !(t.safe === named && t.date === namedDate));
  const leaving = closingSafeNames(closing);
  if (leaving.size === 0) return rows.slice(0, limit);
  // A target whose season is ending keeps its place in this list even when the
  // cap would have cut it: the card above has just said a clear night on it buys
  // something the rest of the year can't, and `plan.targets` is ordered by date,
  // so the one row that cannot wait is exactly the one a later-in-the-week night
  // pushes over the edge. Filling around it keeps the list the same length.
  const kept = rows.filter((t) => leaving.has(t.safe)).slice(0, limit);
  const room = limit - kept.length;
  const fill = room > 0
    ? rows.filter((t) => !leaving.has(t.safe)).slice(0, room)
    : [];
  const chosen = new Set([...kept, ...fill]);
  // Re-read in `plan.targets`' own order so the line still runs soonest-first;
  // promoting a row must not reorder the ones around it.
  return rows.filter((t) => chosen.has(t));
}

/** The `safe` names the season-closing plan is naming, or an empty set. */
function closingSafeNames(closing: SeasonClosing | null | undefined): Set<string> {
  return new Set((closing?.targets ?? []).map((t) => t.safe));
}

/**
 * The closing-season row for a target, when the plan names it — so a caller can
 * say *why* a row matters without re-deriving the season arithmetic.
 */
export function closingRowFor(
  safe: string, closing: SeasonClosing | null | undefined,
): ClosingTarget | null {
  return (closing?.targets ?? []).find((t) => t.safe === safe) ?? null;
}

/** "M 31 — Thursday", and "M 27 — Tuesday (about 2 weeks left)" for a target
 *  whose season is ending.
 *
 * The suffix borrows `weeksLeftPhrase` rather than wording a second countdown,
 * so this line and the "Shoot these before they're gone" card above it cannot
 * come to two different opinions about how long is left. Bracketed rather than
 * separated by the " · " the caller joins rows with, which would have made one
 * row read as two.
 */
export function targetNightPhrase(
  t: TargetBestNight, now: Date, season?: ClosingTarget | null,
): string {
  const base = `${t.name} — ${weekNightLabel(t.date, now)}`;
  return season ? `${base} (${weeksLeftPhrase(season.weeks_left)})` : base;
}

/**
 * The one sentence that stops this card and "Shoot these before they're gone"
 * prescribing different nights without acknowledging each other — or `null`
 * when there is nothing to reconcile.
 *
 * The two cards sit adjacent on the Tonight page and are both true. The card
 * above argues that *"a clear night spent on one of these buys something the
 * rest of the year can't"*; this one answers "which night should I go out?" with
 * `plan_week`'s score, which is pure observability (altitude and Moon) and knows
 * nothing about a season ending. So on any week where the best-placed target is
 * not the one that is leaving, the reader is handed two prescriptions and the
 * fact that would let them choose — that one of those nights does not come round
 * again — is stated on neither card.
 *
 * Silent in all three cases where there is no tension: no closing plan (an older
 * backend, or nothing leaving — which is most of the year), nothing leaving that
 * is also placed this week, and the headline already naming the leaving target.
 */
export function closingWeekNote(
  plan: PlanWeek, closing: SeasonClosing | null | undefined, now: Date,
): string | null {
  const rows = closing?.targets ?? [];
  if (rows.length === 0) return null;
  const headlineSafe = bestNightOfWeek(plan.nights)?.best?.safe;
  for (const season of rows) {       // soonest to leave first, as served
    if (season.safe === headlineSafe) return null;   // the cards already agree
    const night = plan.targets.find((t) => t.safe === season.safe);
    if (!night) continue;
    return `${season.name} is on its way out of your sky — ${weeksLeftPhrase(season.weeks_left)}.`
      + ` Its best night this week is ${weekNightLabelInline(night.date, now)}`
      + " — and unlike the others here, that one doesn't come round again.";
  }
  return null;
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

/**
 * How long that night's darkness is — *or*, for a night already under way, how
 * much of it is left. "8.3 h dark" / "5.9 h left".
 *
 * The planner clips an ongoing window to "now" so it never offers darkness that
 * has already gone (`upcoming_dark_windows`), which makes the first row's number
 * a different quantity from every other row's — and from the Tonight page's own
 * header, which quotes the *whole* night ("8.3 h of darkness") a few inches
 * above. Printing both as "N dark" left one page saying a night is 8.3 h and
 * 5.9 h long at the same time. "left" is the word the Dashboard's "About 2 h of
 * dark sky left tonight" already uses for exactly this number, so the app keeps
 * one vocabulary rather than inventing a second.
 *
 * An older backend sends no flag, and "how long is this night" is the right
 * reading of every un-flagged row — so the wording is unchanged there.
 */
export function weekDarkPhrase(night: WeekNight): string {
  const span = formatMinutes(night.dark_minutes);
  return night.dark_in_progress === true ? `${span} left` : `${span} dark`;
}
