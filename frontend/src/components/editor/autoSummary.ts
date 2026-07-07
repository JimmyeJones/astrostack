import type { AutoAnalysis, EditOp, OpInstance } from "../../api/client";

/** Plain-language phrase for each editor op id the Auto-process recipe can emit,
 * so a user sees *what Auto did* (and in what order) instead of a bare list of op
 * names. Keyed by op id; any op not listed falls back to its registry label. */
const OP_PHRASES: Record<string, string> = {
  "background.level_coverage": "evened out the mosaic panel brightness",
  "background.final_gradient": "flattened the background",
  "background.subtract": "removed the background gradient",
  "tone.color_calibrate": "balanced the colour",
  "detail.denoise": "reduced noise",
  "tone.stretch": "applied a natural stretch",
  "tone.curves": "added a gentle contrast curve",
  "tone.scnr": "removed the green cast",
  "tone.saturation": "boosted colour saturation",
  "detail.sharpen": "sharpened detail",
  "detail.deconvolve": "deconvolved to recover sharpness",
  "geometry.crop": "trimmed the ragged mosaic border",
};

/** Ordered plain-language phrases for the *enabled* ops in a recipe, in pipeline
 * order, de-duplicated (a recipe rarely repeats an op, but be safe). Pure — used
 * to explain what Auto-process built. Unknown ops fall back to their registry
 * label (lower-cased), or the raw id when no spec is known, so it degrades
 * gracefully as ops change. */
export function autoSummaryPhrases(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const op of ops) {
    if (!op.enabled) continue;
    const phrase = OP_PHRASES[op.id]
      ?? (specs[op.id]?.label ? specs[op.id].label.toLowerCase() : op.id);
    if (seen.has(phrase)) continue;
    seen.add(phrase);
    out.push(phrase);
  }
  return out;
}

/** Compact number for a value note: up to 2 decimals, no trailing-zero padding
 * (0.2 → "0.2", 1.05 → "1.05", 1.5 → "1.5"). */
function fmt(n: number): string {
  return String(Math.round(n * 100) / 100);
}

/** The *data-driven values* Auto picked from your image, read straight from the
 * built recipe's op params — this is where Auto's adaptivity actually lives, so
 * surfacing it turns "it did something" into "it did *this*, because of my data".
 * Pure; returns phrases in pipeline order for the *enabled*, value-bearing ops
 * only (STF sky level, denoise strength, saturation, sharpen radius), skipping
 * any whose param is missing/non-numeric so it degrades gracefully. */
export function autoValuePhrases(ops: OpInstance[]): string[] {
  const out: string[] = [];
  for (const op of ops) {
    if (!op.enabled) continue;
    const p = (op.params ?? {}) as Record<string, unknown>;
    if (op.id === "tone.stretch" && p.mode === "stf" && typeof p.target_bg === "number") {
      out.push(`sky level ${fmt(p.target_bg)}`);
    } else if (op.id === "detail.denoise" && typeof p.strength === "number") {
      out.push(`denoise strength ${fmt(p.strength)}`);
    } else if (op.id === "tone.saturation" && typeof p.amount === "number") {
      out.push(`saturation ${fmt(p.amount)}×`);
    } else if (op.id === "detail.sharpen" && typeof p.radius === "number") {
      // The Auto crossfade eases the sharpen strength below its full 0.5 on
      // noisier stacks, so surface it when reduced (it's data-driven then).
      if (typeof p.amount === "number" && p.amount < 0.5) {
        out.push(`sharpen radius ${fmt(p.radius)} px (strength ${fmt(p.amount)})`);
      } else {
        out.push(`sharpen radius ${fmt(p.radius)} px`);
      }
    }
  }
  return out;
}

/** A single line naming the values Auto chose from the data, or null when none
 * of the value-bearing ops are present, e.g.
 * "Tuned to your data: sky level 0.2, saturation 1.1×, sharpen radius 1.4 px." */
export function autoValueSentence(ops: OpInstance[]): string | null {
  const phrases = autoValuePhrases(ops);
  if (phrases.length === 0) return null;
  return `Tuned to your data: ${phrases.join(", ")}.`;
}

/** A single friendly sentence describing what Auto-process did, or null when the
 * recipe is empty (nothing to explain). Capitalises the first phrase and joins
 * the rest with commas + a trailing "then" before the last, e.g.
 * "Flattened the background, balanced the colour, then sharpened detail." */
export function autoSummarySentence(
  ops: OpInstance[],
  specs: Record<string, EditOp>,
): string | null {
  const phrases = autoSummaryPhrases(ops, specs);
  if (phrases.length === 0) return null;
  const cap = phrases[0].charAt(0).toUpperCase() + phrases[0].slice(1);
  const rest = phrases.slice(1);
  let body: string;
  if (rest.length === 0) body = cap;
  else if (rest.length === 1) body = `${cap}, then ${rest[0]}`;
  else body = `${cap}, ${rest.slice(0, -1).join(", ")}, then ${rest[rest.length - 1]}`;
  return `${body}.`;
}

/** The *causal inputs* Auto measured from the image to drive its picks — the "why"
 * layer that sits behind `autoSummarySentence` (what it did) and `autoValueSentence`
 * (what values it chose). Turns "Auto did this" into "Auto did this *because your
 * data looked like this*". Pure; reads the `…/editor/auto-analysis` payload, which
 * is nullable field-by-field, so it lists only the cues that were actually
 * measured and returns null when none were (e.g. an unmeasurable proxy with no
 * FWHM), so the note simply omits the line rather than showing an empty one.
 *
 * e.g. "Measured from your image: a ~0.10 sky, 4.7 px stars, some background noise,
 * 12% of ragged mosaic edge to trim."
 */
export function autoCauseSentence(a: AutoAnalysis | null | undefined): string | null {
  if (!a) return null;
  const parts: string[] = [];
  if (typeof a.sky === "number") parts.push(`a ~${fmt(a.sky)} sky`);
  if (typeof a.median_fwhm === "number") parts.push(`${fmt(a.median_fwhm)} px stars`);
  // A qualitative noise read (the numeric σ is opaque to a beginner); only when
  // it actually influenced the recipe (the denoise/sharpen crossfade is engaged).
  if (typeof a.noise_fraction === "number" && a.noise_fraction > 0) {
    parts.push(a.noise_fraction >= 0.75 ? "a noisy background" : "some background noise");
  }
  if (typeof a.trim_fraction === "number" && a.trim_fraction >= 0.005) {
    parts.push(`${Math.round(a.trim_fraction * 100)}% of ragged mosaic edge to trim`);
  }
  if (parts.length === 0) return null;
  const body = parts.length === 1
    ? parts[0]
    : `${parts.slice(0, -1).join(", ")}, ${parts[parts.length - 1]}`;
  return `Measured from your image: ${body}.`;
}
