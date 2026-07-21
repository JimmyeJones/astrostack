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
