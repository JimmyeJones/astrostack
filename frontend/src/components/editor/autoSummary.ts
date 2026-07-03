import type { EditOp, OpInstance } from "../../api/client";

/** Plain-language phrase for each editor op id the Auto-process recipe can emit,
 * so a user sees *what Auto did* (and in what order) instead of a bare list of op
 * names. Keyed by op id; any op not listed falls back to its registry label. */
const OP_PHRASES: Record<string, string> = {
  "background.final_gradient": "flattened the background",
  "background.subtract": "removed the background gradient",
  "tone.color_calibrate": "balanced the colour",
  "detail.denoise": "reduced noise",
  "tone.stretch": "applied a natural stretch",
  "tone.curves": "adjusted the tone curve",
  "tone.scnr": "removed the green cast",
  "tone.saturation": "boosted colour saturation",
  "detail.sharpen": "sharpened detail",
  "detail.deconvolve": "deconvolved to recover sharpness",
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
