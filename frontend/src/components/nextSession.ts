/** Pure helpers for the "Plan your next night" card.
 *
 * The forward-looking companion to the retrospective trend cards: it joins the
 * readiness card's goal *gap* ("you're ~2 h short of a good M31") with the night
 * planner's next dark *window* ("…and Thursday 22:40 → 02:10 is when to shoot it")
 * into one plain, dated next step. All phrasing lives here (no React, no I/O) so
 * it's unit-testable in isolation. Times are UTC — shown as UTC to match the other
 * planner cues and stay honest across the viewer's own timezone.
 */
import type { NextObservingWindow } from "../api/client";
import { formatClockUtc } from "./focusTrend";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** "Thu 15 Jan" (UTC) from an ISO timestamp, or "" if unparseable. */
export function formatWindowDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${WEEKDAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
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

/** One window as a dated, plain-language line:
 * "Thu 15 Jan, 22:40 → 02:10 UTC — climbs to 34°, thin Moon (12%)." */
export function describeWindow(w: NextObservingWindow): string {
  const date = formatWindowDate(w.dark_start_utc);
  const start = formatClockUtc(w.usable_start_utc ?? w.dark_start_utc);
  const end = formatClockUtc(w.usable_end_utc ?? w.dark_end_utc);
  const alt = Math.round(w.max_altitude_deg);
  const moon = moonPhrase(w);
  const timeClause = start && end ? `${start} → ${end} UTC` : "after dark";
  return `${date}, ${timeClause} — climbs to ${alt}°, ${moon}.`;
}

/** A short heading for the window list: the soonest window is "your next good
 * window"; extra windows (when the goal needs more than one night) are "then". */
export function windowsIntro(count: number): string {
  return count > 1 ? "Your next good windows:" : "Your next good window:";
}
