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

/**
 * A date label that is a **capture** date — when the light was collected — and
 * not when the app did something. Only {@link formatCaptureNights} can make one.
 *
 * It is a plain string at runtime (a branded type, erased by the compiler), so
 * it renders and concatenates like any other. The point is the *input* side:
 * `sharePictureText` takes one of these, so handing it
 * `formatStampDate(run.timestamp_utc)` — the moment the stack ran — no longer
 * type-checks. That mistake was made twice on the Target page and survived a
 * whole sweep of this class, because a processing stamp reads perfectly
 * plausibly in the slot a capture date belongs in.
 */
export type CaptureLabel = string & { readonly __captureLabel: unique symbol };

/**
 * When a picture's subs were **shot**, from a run's capture window
 * (`capture_night_start` / `capture_night_end` — observing-night dates the
 * server bucketed with the same noon-to-noon rule the Nights card uses).
 *
 * A stack's own `timestamp_utc` is when it *ran*, which is a different fact: on
 * a re-stack of a back catalogue the two are years apart, so nothing may say
 * "shot" or "captured" from that stamp. Returns `""` — not "—" — when the window
 * is missing or unparseable (every run from before the app recorded it), because
 * every caller here drops the clause rather than printing a placeholder.
 *
 * Compact by design, for a caption or a tile: the shared parts of a range are
 * written once ("15–18 Nov 2024", "28 Oct – 3 Nov 2024", "28 Dec 2024 – 3 Jan
 * 2025"). The en dash is spaced only when the two sides are multi-word, which is
 * the typographic convention and keeps "15–18" from looking like a subtraction.
 */
export function formatCaptureNights(
  start: string | null | undefined,
  end: string | null | undefined,
): CaptureLabel {
  const a = parseNightDate(start) ?? parseNightDate(end);
  const b = parseNightDate(end) ?? parseNightDate(start);
  if (!a || !b) return "" as CaptureLabel;
  const [first, last] = nightKey(a) <= nightKey(b) ? [a, b] : [b, a];
  const lastLabel = `${last.day} ${MONTHS_ABBR[last.month - 1]} ${last.year}`;
  if (nightKey(first) === nightKey(last)) return lastLabel as CaptureLabel;
  if (first.year !== last.year) {
    return `${first.day} ${MONTHS_ABBR[first.month - 1]} ${first.year} – ${lastLabel}` as CaptureLabel;
  }
  if (first.month !== last.month) {
    return `${first.day} ${MONTHS_ABBR[first.month - 1]} – ${lastLabel}` as CaptureLabel;
  }
  return `${first.day}–${lastLabel}` as CaptureLabel;
}

/**
 * The same window as a caption clause: `"on 15 Nov 2024"` for one night,
 * `"between 15 and 18 Nov 2024"` for a run built from several — and
 * `"over 4 nights, between 15 and 18 Nov 2024"` when the run also recorded how
 * many nights it is made of. `""` when unknown, so the caption drops the clause.
 *
 * The count is the part a person actually says out loud about their picture, and
 * a window cannot supply it: 15→18 Nov is equally consistent with two nights and
 * with four. So it is quoted only when the run *recorded* it (`capture_nights`,
 * schema 19+) — never inferred from the span, which would turn a two-night stack
 * into a four-night boast.
 */
export function captureNightsClause(
  start: string | null | undefined,
  end: string | null | undefined,
  nights?: number | null,
): string {
  const a = parseNightDate(start) ?? parseNightDate(end);
  const b = parseNightDate(end) ?? parseNightDate(start);
  if (!a || !b) return "";
  const [first, last] = nightKey(a) <= nightKey(b) ? [a, b] : [b, a];
  const lastLabel = `${last.day} ${MONTHS_ABBR[last.month - 1]} ${last.year}`;
  if (nightKey(first) === nightKey(last)) return `on ${lastLabel}`;
  const firstLabel = first.year !== last.year
    ? `${first.day} ${MONTHS_ABBR[first.month - 1]} ${first.year}`
    : first.month !== last.month
      ? `${first.day} ${MONTHS_ABBR[first.month - 1]}`
      : `${first.day}`;
  const span = `between ${firstLabel} and ${lastLabel}`;
  // A count of 1 beside a multi-night span would contradict it, and a count is
  // only ever a whole number of nights — anything else is a backend the app
  // doesn't understand, so it says nothing rather than something odd.
  const n = typeof nights === "number" && Number.isInteger(nights) && nights > 1
    ? nights : null;
  return n ? `over ${n} nights, ${span}` : span;
}

/**
 * The one-line date under a picture, **labelled** — `"Shot 15 Nov 2024"` when
 * the run recorded when its subs were taken, `"Stacked 30 Aug 2026"` when it
 * didn't, and `""` when neither date is usable.
 *
 * The label is the point. A *bare* date beside a picture is read as "the night
 * I took this", and on every strip and slideshow in the app that date was the
 * run's `timestamp_utc` — so a re-stack of a 2024 back catalogue was captioned
 * with today. Naming which date it is costs one word and makes the wrong
 * reading impossible; preferring the capture window means the common case says
 * the thing the reader actually wanted.
 */
export function pictureDateLabel(
  captureNightStart: string | null | undefined,
  captureNightEnd: string | null | undefined,
  stackedUtc: string | null | undefined,
): string {
  const shot = formatCaptureNights(captureNightStart, captureNightEnd);
  if (shot) return `Shot ${shot}`;
  const stacked = formatStampDate(stackedUtc);
  return stacked ? `Stacked ${stacked}` : "";
}

/** Sortable `YYYYMMDD` for a parsed night, so two nights compare as dates. */
function nightKey(p: { year: number; month: number; day: number }): number {
  return p.year * 10000 + p.month * 100 + p.day;
}

/**
 * A byte count as a friendly disk figure: "21 GB" / "4.2 GB" / "830 MB".
 *
 * Binary (1024³), because that is what every other size this app prints uses —
 * the Storage page's per-target breakdown and `df -h` both do — and because the
 * *only* thing that matters is that all of them agree. The server also serves
 * pre-rounded decimal `*_gb` fields (1e9); rendering one figure from those and
 * another from raw bytes is how the Storage page came to show "23 GB free on
 * disk" directly above "21 GB free — not enough imaging history yet".
 */
export function formatDiskSize(bytes: number): string {
  const gb = bytes / 1024 ** 3;
  if (gb >= 10) return `${gb.toFixed(0)} GB`;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / 1024 ** 2;
  return `${mb.toFixed(0)} MB`;
}

/**
 * A picture's date, in the viewer's own locale but never ambiguous: "16 Aug
 * 2026" / "Aug 16, 2026", **never** "8/16/2026".
 *
 * This is for a *moment* — when a stack was run, when a still was made — which
 * is why it goes through `Date` and shows local time, unlike `formatNightDate`
 * above (an observing night is a date already, and must not shift). The one
 * thing it will not do is print the month as a number: half the world reads
 * 8/16 as the 8th of month 16, and the app puts these captions on the same
 * screen as "15 Nov 2024" from the night surfaces, so a bare
 * `toLocaleDateString()` made two dates on one page disagree about their own
 * format. Empty string for a missing or unparseable stamp, so a caller can drop
 * the clause rather than print "Invalid Date".
 */
export function formatStampDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, {
    day: "numeric", month: "short", year: "numeric",
  });
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
