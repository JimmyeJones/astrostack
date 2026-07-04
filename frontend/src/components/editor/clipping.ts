import type { Histogram } from "../../api/client";

/** Fraction (0..1) of a channel's pixels piled into one histogram bin. */
function binFraction(counts: number[] | undefined, bin: number): number {
  if (!counts || !counts.length) return 0;
  let total = 0;
  for (const c of counts) total += c;
  if (total <= 0) return 0;
  const idx = bin < 0 ? counts.length + bin : bin;
  return (counts[idx] ?? 0) / total;
}

// The editor histogram clips values into [0, 1], so every blown-white pixel
// lands in the top bin and every crushed-black pixel in the bottom bin. A large
// pile in an extreme bin means the stretch/levels have pushed detail past the
// point of no return on export. Highlights are the reliable, most-damaging case
// (blown star/nebula cores), so it trips at a low threshold; a crushed-shadow
// warning needs a much larger pile to avoid nagging on legitimately dark skies.
const HIGHLIGHT_CLIP_FRAC = 0.02;
const SHADOW_CLIP_FRAC = 0.35;

function pct(frac: number): string {
  const p = frac * 100;
  return p < 1 ? "<1%" : `${Math.round(p)}%`;
}

/** Which extreme(s) the current recipe is clipping into, from the live
 * histogram: ``high`` = a damaging pile of pure-white pixels (blown star/nebula
 * cores), ``low`` = the sky crushed to pure black. Uses the same thresholds as
 * :func:`clippingCaption` so the caption and the histogram clip-edge guides can
 * never disagree. Pure and side-effect free. */
export function clippingEdges(
  hist: Histogram | undefined,
): { high: boolean; low: boolean } {
  if (!hist) return { high: false, low: false };
  const high = Math.max(
    binFraction(hist.r, -1), binFraction(hist.g, -1), binFraction(hist.b, -1));
  const low = Math.max(
    binFraction(hist.r, 0), binFraction(hist.g, 0), binFraction(hist.b, 0));
  return { high: high >= HIGHLIGHT_CLIP_FRAC, low: low >= SHADOW_CLIP_FRAC };
}

/** A plain-language warning when the current recipe clips highlights or shadows,
 * or ``null`` when the histogram looks healthy. Built from the already-fetched
 * live histogram — advisory only, it changes nothing. Highlights (blown white)
 * take priority as the more damaging, more reliable signal; a badly crushed
 * shadow is mentioned too. Pure and side-effect free. */
export function clippingCaption(hist: Histogram | undefined): string | null {
  if (!hist) return null;
  const high = Math.max(
    binFraction(hist.r, -1), binFraction(hist.g, -1), binFraction(hist.b, -1));
  const low = Math.max(
    binFraction(hist.r, 0), binFraction(hist.g, 0), binFraction(hist.b, 0));
  const parts: string[] = [];
  if (high >= HIGHLIGHT_CLIP_FRAC) {
    parts.push(
      `Highlights are clipping — about ${pct(high)} of pixels are pure white. `
      + "Ease the stretch or lower the white point to keep star-core and "
      + "bright-nebula detail.");
  }
  if (low >= SHADOW_CLIP_FRAC) {
    parts.push(
      `Shadows are clipping — about ${pct(low)} of pixels are crushed to black. `
      + "Raise the black point gently or ease the stretch to keep faint detail.");
  }
  return parts.length ? parts.join(" ") : null;
}
