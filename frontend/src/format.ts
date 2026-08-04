// Shared display formatters.

// Format an integration time in seconds as a friendly "2.3 h" / "42 min" / "8 s"
// so a beginner reads total exposure at a glance instead of a raw second count.
export function formatIntegration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "—";
  // Promote a value that *rounds* up to a full unit rather than printing it in
  // the smaller unit ("60 min" / "60 s"): pick the unit, then re-check that the
  // rounded figure still fits it, else roll into the next unit.
  if (seconds < 60) {
    const s = Math.round(seconds);
    if (s < 60) return `${s} s`;
    seconds = 60;  // rounds up to a whole minute
  }
  if (seconds < 3600) {
    const m = Math.round(seconds / 60);
    if (m < 60) return `${m} min`;
    seconds = 3600;  // rounds up to a whole hour
  }
  return `${(seconds / 3600).toFixed(seconds >= 36000 ? 0 : 1)} h`;
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// Format an ISO-8601 UTC timestamp as a friendly "Month Year" (e.g.
// "January 2026") for the "first light" line. We read the year/month straight
// off the string rather than via Date, so the label never shifts across a
// timezone boundary (the stamp is already UTC and we only want the month).
export function formatMonthYear(iso: string | null | undefined): string {
  if (!iso) return "—";
  const m = /^(\d{4})-(\d{2})/.exec(iso);
  if (!m) return "—";
  const monthIdx = parseInt(m[2], 10) - 1;
  if (monthIdx < 0 || monthIdx > 11) return "—";
  return `${MONTH_NAMES[monthIdx]} ${m[1]}`;
}

const MONTHS_ABBR = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/**
 * A friendly night date ("8 Jul 2026") from an ISO-8601 date or UTC stamp. We
 * read the date parts straight off the string rather than via `Date`, so the
 * night label never shifts across a timezone boundary (mirrors
 * `formatMonthYear`). Re-exported from `NightsCard` for its long-standing
 * callers; it lives here so the recency helpers below can share one month table.
 */
export function formatNightDate(iso: string | null | undefined): string {
  const p = parseNightDate(iso);
  return p ? `${p.day} ${MONTHS_ABBR[p.month - 1]} ${p.year}` : "—";
}

/** The `YYYY-MM-DD` head of an ISO date/stamp, validated. `null` when absent or
 *  malformed, so every caller can distinguish "no night" from a real one. */
function parseNightDate(
  iso: string | null | undefined,
): { year: number; month: number; day: number } | null {
  if (!iso) return null;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return null;
  const year = parseInt(m[1], 10);
  const month = parseInt(m[2], 10);
  const day = parseInt(m[3], 10);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

/**
 * Whole calendar days between an observing night and *today*, or `null` when the
 * night can't be dated.
 *
 * 0 = tonight's own session, 1 = the night just gone, 14 = a fortnight ago. Both
 * sides are compared as plain calendar dates (the night bucket the server sends
 * is already a *local* noon-to-noon date, and `now` is read in the browser's
 * local zone), so no timezone arithmetic can shift the answer by a day.
 */
export function nightAgeDays(
  iso: string | null | undefined,
  now: Date = new Date(),
): number | null {
  const p = parseNightDate(iso);
  if (!p) return null;
  const night = Date.UTC(p.year, p.month - 1, p.day);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  if (!Number.isFinite(night) || !Number.isFinite(today)) return null;
  return Math.round((today - night) / 86_400_000);
}

/**
 * Is this night recent enough that calling it "last night" is honest?
 *
 * True for tonight's own session and the night just gone — and for a night we
 * can't date at all (an older backend, or frames with no capture time), so the
 * warm wording is only ever *replaced* when we have a real date to replace it
 * with. A night stamped in the future (a clock skew) also keeps the warm
 * wording rather than announcing a date that hasn't happened.
 */
export function isRecentNight(
  iso: string | null | undefined,
  now: Date = new Date(),
): boolean {
  const age = nightAgeDays(iso, now);
  return age === null || age <= 1;
}

/**
 * A night as a short in-sentence date — "8 Jul", or "8 Jul 2025" once it's not
 * this year, so an old night is never mistaken for a recent one. `null` when the
 * night can't be dated (callers keep their undated wording).
 */
export function formatNightDayMonth(
  iso: string | null | undefined,
  now: Date = new Date(),
): string | null {
  const p = parseNightDate(iso);
  if (!p) return null;
  const short = `${p.day} ${MONTHS_ABBR[p.month - 1]}`;
  return p.year === now.getFullYear() ? short : `${short} ${p.year}`;
}
