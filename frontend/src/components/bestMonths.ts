/** Pure helpers for the "Best time of year to shoot this" seasonal strip.
 *
 * The plan-ahead companion to "Plan your next night" (which looks ~two weeks
 * out): it turns twelve months of observability (from /api/plan/best-months)
 * into a glanceable heat strip plus one plain-language verdict — "Best around
 * Nov–Feb, highest in December" — so a beginner learns *when this year* a named
 * object is actually up, without leaving the app or already knowing the sky.
 *
 * All phrasing lives here (no React, no I/O) so it's unit-testable in isolation.
 * Month names are used rather than season words ("winter"/"summer") so the
 * verdict is correct in either hemisphere.
 */
import type { MonthObservability } from "../api/client";

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** A per-month ranking score. When the target clears the altitude floor in *some*
 * month, rank by usable dark minutes (the honest "how long can I shoot it?"). When
 * it never clears the floor anywhere (a low-from-here target), fall back to its
 * peak altitude so the strip still shows the seasonal shape — with a caveat in the
 * verdict that it stays low. */
export function monthScore(m: MonthObservability, anyUsable: boolean): number {
  if (anyUsable) return Math.max(0, m.usable_dark_minutes);
  return Math.max(0, m.max_transit_alt_deg);
}

/** Per-cell shading intensity (0..1), normalised against the best month, for the
 * heat strip. All zero when the target never gets above the horizon. */
export function monthShades(months: MonthObservability[]): number[] {
  const anyUsable = months.some((m) => m.usable_dark_minutes > 0);
  const scores = months.map((m) => monthScore(m, anyUsable));
  const max = Math.max(0, ...scores);
  if (max <= 0) return scores.map(() => 0);
  return scores.map((s) => s / max);
}

/** The longest run of `true` in a *circular* 12-element flag array (seasons wrap
 * Dec→Jan). Returns 1-indexed inclusive month bounds and the run length, or null
 * when nothing is flagged. A full year of `true` returns Jan–Dec (length 12). */
export function longestCircularRun(
  flags: boolean[],
): { start: number; end: number; length: number } | null {
  const n = flags.length;
  if (n === 0 || !flags.some((f) => f)) return null;
  if (flags.every((f) => f)) return { start: 1, end: n, length: n };
  let best = { start: 1, end: 1, length: 0 };
  // Walk the doubled array so a run that wraps past the end is seen whole.
  let runStart = 0;
  let runLen = 0;
  for (let i = 0; i < n * 2; i++) {
    if (flags[i % n]) {
      if (runLen === 0) runStart = i;
      runLen++;
      if (runLen > best.length && runLen <= n) {
        best = {
          start: (runStart % n) + 1,
          end: ((runStart + runLen - 1) % n) + 1,
          length: runLen,
        };
      }
    } else {
      runLen = 0;
    }
  }
  return best;
}

/** Format a 1-indexed month range as "Nov–Feb", or a single month as "Dec". */
export function formatMonthRange(start: number, end: number): string {
  if (start === end) return MONTHS[start - 1];
  return `${MONTHS[start - 1]}–${MONTHS[end - 1]}`;
}

export interface BestMonthsVerdict {
  /** Plain-language sentence(s) a beginner can act on. */
  text: string;
  /** The single best month (1..12) to highlight on the strip, or null when the
   * target is never observable. */
  peakMonth: number | null;
  /** Per-cell shading (0..1), 12 values, aligned to Jan..Dec. */
  shades: number[];
}

/** Turn twelve months of observability into a verdict + strip shading. Returns
 * null for a malformed (not-12-row) input so the caller self-hides. */
export function bestMonthsVerdict(
  months: MonthObservability[],
): BestMonthsVerdict | null {
  if (months.length !== 12) return null;

  const shades = monthShades(months);
  const anyAboveHorizon = months.some((m) => m.max_transit_alt_deg > 0);
  if (!anyAboveHorizon) {
    return {
      text: "This target never climbs above the horizon from your location, so it can't be imaged from here.",
      peakMonth: null,
      shades,
    };
  }

  const anyUsable = months.some((m) => m.usable_dark_minutes > 0);
  const scores = months.map((m) => monthScore(m, anyUsable));
  const maxScore = Math.max(0, ...scores);
  // Peak month: the highest score, earliest on ties (deterministic).
  let peakIdx = 0;
  for (let i = 1; i < 12; i++) if (scores[i] > scores[peakIdx]) peakIdx = i;
  const peakMonth = peakIdx + 1;
  const peakName = MONTHS[peakIdx];

  // "Good" months: those actually usable (clearing the floor in darkness). When
  // nothing ever clears the floor, fall back to the months within reach of the
  // altitude peak so the strip still names a season, with a low-target caveat.
  const good = anyUsable
    ? months.map((m) => m.usable_dark_minutes > 0)
    : scores.map((s) => s >= 0.6 * maxScore);

  const goodCount = good.filter(Boolean).length;
  const lowCaveat = anyUsable
    ? ""
    : " It stays low in your sky even at its best, so it'll be a tougher target from here.";

  if (goodCount >= 12) {
    return {
      text: `Up all year — this target never sets from your location, so any clear night works (highest around ${peakName}).${lowCaveat}`,
      peakMonth,
      shades,
    };
  }

  const run = longestCircularRun(good);
  const rangeStr = run ? formatMonthRange(run.start, run.end) : peakName;
  const single = !run || run.start === run.end;
  const best = single
    ? `Best around ${rangeStr}.`
    : `Best around ${rangeStr}, highest in ${peakName}.`;

  // Name the out-of-reach stretch too, so the beginner knows when not to bother.
  const badRun = longestCircularRun(good.map((g) => !g));
  const lowClause =
    badRun && badRun.length >= 2
      ? ` Low or out of reach ${formatMonthRange(badRun.start, badRun.end)}.`
      : "";

  return { text: `${best}${lowClause}${lowCaveat}`, peakMonth, shades };
}

/** A short label + full month name for a strip cell's tooltip/aria. */
export function monthLabel(month: number): string {
  return MONTHS[month - 1] ?? "";
}
