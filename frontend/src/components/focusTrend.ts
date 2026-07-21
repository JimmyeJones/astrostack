/** Pure helpers for the "Focus & sharpness through the night" trend card.
 *
 * All phrasing + the sparkline geometry live here (no React, no I/O) so they're
 * unit-testable in isolation, mirroring NightsCard's pure `verdictBadge` split.
 */
import type { FocusTrend } from "../api/client";

/** UTC clock "HH:MM" read straight off an ISO-8601 stamp (no `Date`, so it never
 *  shifts across a timezone boundary — matches NightsCard's `formatNightDate`). */
export function formatClockUtc(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : null;
}

const px = (v: number) => `${v.toFixed(1)} px`;

/** Badge colour + label for a focus verdict. Pure/testable. */
export function focusVerdictBadge(verdict: string): { color: string; label: string } {
  switch (verdict) {
    case "softened":
      return { color: "yellow", label: "softened" };
    case "improved":
      return { color: "teal", label: "sharpened up" };
    default:
      return { color: "teal", label: "steady" };
  }
}

/** Plain-language, beginner-facing sentence for the card. Pure/testable. */
export function describeFocusTrend(t: FocusTrend): string {
  switch (t.verdict) {
    case "softened": {
      const when = formatClockUtc(t.soft_after_utc);
      const whenClause = when ? ` after ${when} UTC` : " later in the night";
      return (
        `Your stars softened${whenClause} ` +
        `(${px(t.early_fwhm_px)} → ${px(t.late_fwhm_px)}) — likely dew or a ` +
        `temperature/focus drift. A dew heater or a quick refocus next time helps; ` +
        `those softer subs were automatically counted less in your stack.`
      );
    }
    case "improved":
      return (
        `Your stars sharpened up as the night went on ` +
        `(${px(t.early_fwhm_px)} → ${px(t.late_fwhm_px)}) — focus settled in.`
      );
    default:
      return `Sharp all night — your stars held steady around ${px(t.median_fwhm_px)}.`;
  }
}

/**
 * Map a run of FWHM values to an SVG polyline `points` string inside a
 * `width`×`height` box. Higher FWHM (softer) plots *lower* (larger y) so the
 * intuitive "up = sharper" reading holds. Pure/testable.
 */
export function sparklinePoints(
  fwhms: number[],
  width: number,
  height: number,
  pad = 3,
): string {
  const n = fwhms.length;
  if (n === 0) return "";
  const lo = Math.min(...fwhms);
  const hi = Math.max(...fwhms);
  const span = hi - lo || 1; // flat series → a centred line, no divide-by-zero
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  return fwhms
    .map((v, i) => {
      const x = pad + (n === 1 ? innerW / 2 : (innerW * i) / (n - 1));
      const y = pad + (innerH * (v - lo)) / span; // sharp (low) → top
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
