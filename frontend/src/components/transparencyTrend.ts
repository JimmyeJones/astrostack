/** Pure helpers for the "Clouds & haze through the night" trend card.
 *
 * The transparency sibling of `focusTrend.ts`: all phrasing + the sparkline
 * geometry live here (no React, no I/O) so they're unit-testable in isolation.
 * Direction differs from focus — for transparency *higher* = a clearer sky.
 */
import type { TransparencyTrend } from "../api/client";
import { formatClockUtc } from "./focusTrend";

export { formatClockUtc };

/** Badge colour + label for a transparency verdict. Pure/testable. */
export function transparencyVerdictBadge(verdict: string): { color: string; label: string } {
  switch (verdict) {
    case "degraded":
      return { color: "yellow", label: "clouds rolled in" };
    case "cleared":
      return { color: "teal", label: "cleared up" };
    default:
      return { color: "teal", label: "clear all night" };
  }
}

/** Plain-language, beginner-facing sentence for the card. Pure/testable. */
export function describeTransparencyTrend(t: TransparencyTrend): string {
  switch (t.verdict) {
    case "degraded": {
      const when = formatClockUtc(t.degraded_after_utc);
      const whenClause = when ? ` after ${when} UTC` : " later in the night";
      return (
        `The sky got hazier${whenClause} — clouds or haze rolling in ` +
        `(or your target sinking into thicker air). Those later subs came through ` +
        `a murkier sky and were automatically counted less in your stack; ` +
        `a clearer night will add more real signal.`
      );
    }
    case "cleared":
      return (
        `It started hazy and cleared up as the night went on — ` +
        `your later subs came through a cleaner sky and did the heavy lifting.`
      );
    default:
      return `Clear all night — your sky's transparency held steady, so every sub pulled its weight.`;
  }
}

/**
 * Map a run of transparency values to an SVG polyline `points` string inside a
 * `width`×`height` box. Higher transparency (clearer) plots *higher* (smaller y)
 * so the intuitive "up = clearer" reading holds. Pure/testable.
 */
export function sparklinePoints(
  scores: number[],
  width: number,
  height: number,
  pad = 3,
): string {
  const n = scores.length;
  if (n === 0) return "";
  const lo = Math.min(...scores);
  const hi = Math.max(...scores);
  const span = hi - lo || 1; // flat series → a centred line, no divide-by-zero
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  return scores
    .map((v, i) => {
      const x = pad + (n === 1 ? innerW / 2 : (innerW * i) / (n - 1));
      const y = pad + (innerH * (hi - v)) / span; // clear (high) → top
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
