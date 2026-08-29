/** Pure helpers for the "Plan your next night" card.
 *
 * The forward-looking companion to the retrospective trend cards: it joins the
 * readiness card's goal *gap* ("you're ~2 h short of a good M31") with the night
 * planner's next dark *window* ("…and Thursday 22:40 → 02:10 is when to shoot it")
 * into one plain, dated next step. All phrasing lives here (no React, no I/O) so
 * it's unit-testable in isolation. Times are shown in the viewer's *local* clock —
 * matching the adjacent "Point here tonight" card and the local calendar an owner
 * actually plans around — with the UTC equivalent kept as a hover tooltip. (An
 * earlier version formatted everything in UTC, which named the wrong night for any
 * owner west of UTC: a `dark_start` of 06:17 UTC is the previous evening locally,
 * so the card said "Mon 27 Jul" for what is Sunday night in Seattle and disagreed
 * with its own .ics file and the neighbouring card.)
 */
import type { NextObservingWindow } from "../api/client";
import { formatClockUtc } from "./focusTrend";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "Thu 15 Jan" in the viewer's *local* timezone from an ISO timestamp, or "" if
 * unparseable. The night is labelled by the local date of its dark-start, so an
 * owner west of UTC sees the evening they'll actually be out (not the UTC date,
 * which rolls over around local sunset for the Americas). */
export function formatWindowDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** "Thu 15 Jan" in UTC, for the hover tooltip that keeps the honest UTC anchor. */
export function formatWindowDateUtc(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** Local wall-clock "HH:MM" (24-h) for a UTC ISO stamp, or null if unparseable. */
export function formatClockLocal(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** How many more subs the goal gap needs, given the target's typical sub length.
 * null when either input is unknown/non-positive (no honest number to show). */
export function subsToGo(
  gapSeconds: number,
  subExposureSeconds: number | null | undefined,
): number | null {
  if (!(gapSeconds > 0)) return null;
  if (typeof subExposureSeconds !== "number" || !(subExposureSeconds > 0)) return null;
  return Math.ceil(gapSeconds / subExposureSeconds);
}

/** The gap phrased in plain hours, e.g. "About 2 more clear hours" / "About 40
 * more clear minutes". Rounds to a friendly figure — this is a rough steer, not a
 * stopwatch. Assumes gapSeconds > 0 (the card only renders then). */
export function formatGapHours(gapSeconds: number): string {
  const mins = Math.round(gapSeconds / 60);
  if (mins < 90) {
    // Under ~1.5 h, minutes read more naturally, rounded to the nearest 10.
    const rounded = Math.max(10, Math.round(mins / 10) * 10);
    return `About ${rounded} more clear minutes`;
  }
  const hours = gapSeconds / 3600;
  // Nearest half-hour for a gentle "about N h" / "about N.5 h".
  const halfSteps = Math.round(hours * 2) / 2;
  return `About ${halfSteps} more clear hours`;
}

/** The lead sentence: the goal gap, with a subs figure when we can estimate one.
 * e.g. "About 2 more clear hours (~120 more subs) for a good picture of this target." */
export function describeGap(
  gapSeconds: number,
  subExposureSeconds: number | null | undefined,
): string {
  const subs = subsToGo(gapSeconds, subExposureSeconds);
  const subsClause = subs != null ? ` (~${subs} more subs)` : "";
  return `${formatGapHours(gapSeconds)}${subsClause} for a good picture of this target.`;
}

/** How bright/relevant the Moon is during a window, or "" when it doesn't matter.
 * A faint Moon (or one that's down while the target is up) is worth reassuring the
 * beginner about; a bright close Moon is worth flagging. */
export function moonPhrase(w: NextObservingWindow): string {
  const pct = Math.round((w.moon_illumination ?? 0) * 100);
  const up = w.moon_up_fraction;
  if (up != null && up <= 0.05) return "Moon out of the way";
  if (pct <= 15) return `thin Moon (${pct}%)`;
  if (up != null && up <= 0.4) return `Moon ${pct}% but mostly down`;
  if (pct >= 65) return `bright Moon (${pct}%)`;
  return `Moon ${pct}%`;
}

/** One window as a dated, plain-language line in the viewer's *local* clock:
 * "Thu 15 Jan, 22:40 → 02:10 — climbs to 34°, thin Moon (12%)." (The UTC anchor
 * lives in {@link windowUtcTooltip}, shown on hover.) */
export function describeWindow(w: NextObservingWindow): string {
  const date = formatWindowDate(w.dark_start_utc);
  const start = formatClockLocal(w.usable_start_utc ?? w.dark_start_utc);
  const end = formatClockLocal(w.usable_end_utc ?? w.dark_end_utc);
  const alt = Math.round(w.max_altitude_deg);
  const moon = moonPhrase(w);
  const timeClause = start && end ? `${start} → ${end}` : "after dark";
  return `${date}, ${timeClause} — climbs to ${alt}°, ${moon}.`;
}

/** The same window's date + times in UTC, for the hover tooltip — so the local
 * line stays honest about the underlying UTC anchor the .ics file also uses:
 * "In UTC: Thu 15 Jan, 22:40 → 02:10". */
export function windowUtcTooltip(w: NextObservingWindow): string {
  const date = formatWindowDateUtc(w.dark_start_utc);
  const start = formatClockUtc(w.usable_start_utc ?? w.dark_start_utc);
  const end = formatClockUtc(w.usable_end_utc ?? w.dark_end_utc);
  const timeClause = start && end ? `${start} → ${end}` : "after dark";
  return `In UTC: ${date}, ${timeClause}`;
}

/** A short heading for the window list: the soonest window is "your next good
 * window"; extra windows (when the goal needs more than one night) are "then". */
export function windowsIntro(count: number): string {
  return count > 1 ? "Your next good windows:" : "Your next good window:";
}

/**
 * "When will I finish this?" — the one thing the card leaves hanging.
 *
 * The app already knows how many more clear nights the goal needs (the readiness
 * card's own `estimateClearNights`, from this target's *own* recent pace) and
 * which upcoming nights this object is genuinely well-placed (the planner's
 * altitude- and Moon-aware windows). Neither alone answers the beginner's actual
 * question, and the night *count* on its own quietly misleads: "2 more nights"
 * reads as "the day after tomorrow" when the object is Moon-washed or too low
 * until the week after. Joining them names the date.
 *
 * Deliberately conditional on the weather ("if the next clear ones cooperate"),
 * because the planner knows altitude and Moon and knows nothing about cloud.
 *
 * Returns null — say nothing rather than guess — when there's no night estimate,
 * when the goal is already met, or when the goal needs more nights than the
 * planner looked ahead for: the windows list is capped, so naming the last one
 * would understate the finish date rather than admit it doesn't know.
 */
export function finishForecast(
  nightsToGo: number | null | undefined,
  windows: NextObservingWindow[] | null | undefined,
): string | null {
  if (typeof nightsToGo !== "number" || !Number.isFinite(nightsToGo)) return null;
  const n = Math.ceil(nightsToGo);
  if (n < 1) return null;
  const wins = windows ?? [];
  if (n > wins.length) return null;
  const date = formatWindowDate(wins[n - 1].dark_start_utc);
  if (!date) return null;
  if (n === 1) {
    return `One more good night should finish this — if ${date} stays clear, `
      + "that could be the one.";
  }
  return `About ${n} more good nights — if the next clear ones cooperate, you `
    + `could finish around ${date}.`;
}
