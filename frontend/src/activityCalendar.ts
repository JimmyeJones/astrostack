/**
 * Pure helpers for the "Your imaging calendar" heatmap.
 *
 * The backend returns one entry per *observing night* it has data for; this turns
 * that sparse list into a dense GitHub-contributions-style grid (weeks as
 * columns, weekday rows) the card renders, plus the plain-language headline above
 * it. Kept pure and offline so it's unit-testable without rendering — a wrong
 * number here can never erode the "trust the data" promise.
 *
 * All date maths is done in UTC on the ISO `YYYY-MM-DD` strings the API already
 * bucketed (the night boundary was decided server-side), so the grid never
 * shifts a cell across a day when the browser's timezone differs from the site's.
 */

import type { ActivityCalendar, NightActivity } from "./api/client";

/** A single day cell in the heatmap grid. `night` is null on a day with no
 *  imaging (or a padding day before the window starts). `level` is a 0–4 shade
 *  bucket used purely for colour. */
export interface DayCell {
  /** ISO `YYYY-MM-DD`, or null for a leading padding cell before `start_date`. */
  date: string | null;
  night: NightActivity | null;
  level: 0 | 1 | 2 | 3 | 4;
}

const DAY_MS = 86_400_000;

function parseUTC(iso: string): number {
  return Date.parse(`${iso}T00:00:00Z`);
}

function isoOf(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

/** Shade bucket for a night's total capture time. Fixed hour thresholds (not
 *  data-relative) so the same amount of imaging always reads the same colour. */
export function exposureLevel(exposureS: number): 0 | 1 | 2 | 3 | 4 {
  const h = exposureS / 3600;
  if (h <= 0) return 0;
  if (h < 0.5) return 1;
  if (h < 1.5) return 2;
  if (h < 3) return 3;
  return 4;
}

/**
 * Build the dense week-column grid. Columns run oldest→newest; each column is a
 * 7-element array indexed by weekday (0 = Sunday, matching `Date.getUTCDay`).
 * The grid starts on the Sunday on or before `start_date` (leading days before
 * the window are padding cells with `date: null`) and ends at `end_date`.
 */
export function buildCalendarGrid(cal: ActivityCalendar): DayCell[][] {
  const byDate = new Map<string, NightActivity>();
  for (const n of cal.nights) byDate.set(n.date, n);

  const startMs = parseUTC(cal.start_date);
  const endMs = parseUTC(cal.end_date);
  if (!(endMs >= startMs)) return [];

  // Pad back to the start of that week (Sunday) so every column is full height.
  const startDow = new Date(startMs).getUTCDay();
  const gridStartMs = startMs - startDow * DAY_MS;

  const weeks: DayCell[][] = [];
  let cur: DayCell[] = [];
  for (let ms = gridStartMs; ms <= endMs; ms += DAY_MS) {
    const inWindow = ms >= startMs;
    const iso = isoOf(ms);
    const night = inWindow ? byDate.get(iso) ?? null : null;
    cur.push({
      date: inWindow ? iso : null,
      night,
      level: night ? exposureLevel(night.exposure_s) : 0,
    });
    if (cur.length === 7) {
      weeks.push(cur);
      cur = [];
    }
  }
  if (cur.length > 0) {
    while (cur.length < 7) cur.push({ date: null, night: null, level: 0 });
    weeks.push(cur);
  }
  return weeks;
}

/** The plain-language headline above the grid, e.g.
 *  "You've imaged 14 nights this month — best run: 5 clear nights in a row."
 *  Returns "" when there's nothing to celebrate yet (the card shows an empty
 *  state instead). */
export function calendarHeadline(cal: ActivityCalendar): string {
  if (cal.n_nights === 0) return "";
  const nights = (n: number) => `${n} night${n === 1 ? "" : "s"}`;
  const month =
    cal.nights_this_month > 0
      ? `You've imaged ${nights(cal.nights_this_month)} this month`
      : `You've imaged ${nights(cal.n_nights)} in the last ${cal.months} months`;
  if (cal.best_streak_nights >= 2) {
    return `${month} — best run: ${cal.best_streak_nights} clear nights in a row.`;
  }
  return `${month}.`;
}

/** Hover/tooltip label for a single night, e.g.
 *  "12 Jul 2026 · 2.3 h across M31, M42". */
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function nightLabel(night: NightActivity, formatIntegration: (s: number) => string): string {
  const d = new Date(parseUTC(night.date));
  // A deterministic "12 Jul 2026" (locale-independent, always UTC) so the label
  // never shifts a day or reorders with the browser's locale.
  const date = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
  const across =
    night.targets.length > 0 ? ` across ${night.targets.join(", ")}` : "";
  return `${date} · ${formatIntegration(night.exposure_s)}${across}`;
}
