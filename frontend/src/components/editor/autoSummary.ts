import type { AutoAnalysis, EditOp, OpInstance, PresetSuggestion } from "../../api/client";

/** Plain-language phrase for each editor op id the Auto-process recipe can emit,
 * so a user sees *what Auto did* (and in what order) instead of a bare list of op
 * names. Keyed by op id; any op not listed falls back to its registry label.
 *
 * The engine keeps the same table (`seestack/edit/presets.py::_AUTO_OP_PHRASES`)
 * so an auto-edit applied by an *unattended* job can stamp the same note on the
 * History Info panel. The two describe one edit to one person, so they are pinned
 * against `autoOpPhrases.cases.json` from both sides — change a phrase here and
 * the table, and both suites follow.
 */
export const OP_PHRASES: Record<string, string> = {
  "background.level_coverage": "evened out the mosaic panel brightness",
  "background.final_gradient": "flattened the background",
  "background.subtract": "removed the background gradient",
  "tone.color_calibrate": "balanced the colour",
  "detail.denoise": "reduced noise",
  "detail.chroma_denoise": "evened out the patchy sky colour",
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
 * (0.2 → "0.2", 1.05 → "1.05", 1.5 → "1.5") — falling back to 3 decimals when
 * 2 would round a positive number down to "0" (0.001 → "0.001").
 *
 * The fallback exists because a *linear* stack's sky sits well below 0.01: the
 * bundled sample's measured 0.001 sky rendered as "measured a ~0 sky", i.e. the
 * app saying it measured nothing, directly above "stretched sky level 0.24".
 * Three
 * decimals is the precision `analyze_auto_inputs` actually carries, so nothing
 * finer than what was measured is ever invented.
 *
 * Mirrored by `seestack/edit/presets.py::_auto_num`, which writes the same
 * numbers into the same clause when an unattended job stamps the note — pinned
 * from both sides against `autoNum.cases.json`. Exported for that guard.
 */
export function fmt(n: number): string {
  let r = Math.round(n * 100) / 100;
  if (r === 0 && n > 0) r = Math.round(n * 1000) / 1000;
  return String(r);
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
      // "stretched" distinguishes this from the *measured* sky named one line
      // above ("a ~0.001 sky before stretching"): this is the display-space
      // background the stretch aimed for, that one is the linear stack's own
      // level. Both are correct and they differ by two orders of magnitude, so
      // unqualified they read as the panel contradicting itself. The words
      // "sky level" stay, because that is what the control itself is called
      // ("STF sky level"), and the note should name the knob it moved.
      out.push(`stretched sky level ${fmt(p.target_bg)}`);
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
 * "Tuned to your data: stretched sky level 0.2, saturation 1.1×, sharpen
 * radius 1.4 px." */
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
 * e.g. "Measured from your image: a ~0.10 sky before stretching, 4.7 px stars,
 * some background noise, 12% of ragged mosaic edge to trim."
 */
export function autoCauseSentence(a: AutoAnalysis | null | undefined): string | null {
  if (!a) return null;
  const parts: string[] = [];
  // "before stretching" names *which* sky: this is the linear stack's own level,
  // where an ordinary value sits near 0.001, while `autoValueSentence` one line
  // below reports the stretch's display-space target ("stretched sky level
  // 0.24"). Mirrored by `_auto_cause_clause`.
  if (typeof a.sky === "number") parts.push(`a ~${fmt(a.sky)} sky before stretching`);
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

/** A single informational line pointing the user at the built-in preset that best
 * matches the image's content, shown alongside the "What Auto-process did" note. The
 * content-classification chip that offers this preset only appears on an *empty*
 * pipeline, so a user who clicks Auto straight away never learns their image was
 * classified — this surfaces the same hint on the surface they *do* land on. Purely a
 * *suggestion of another starting point*; it never implies the Auto recipe was wrong.
 * Returns null unless the classifier is confident (`preset_id` + `label` present — it
 * declines to null on an ambiguous field), so an unsure classification omits the line.
 *
 * e.g. "Your image looks like a Star cluster — its preset is another good starting
 * point to compare."
 */
export function presetSuggestionSentence(
  s: PresetSuggestion | null | undefined,
): string | null {
  if (!s || !s.preset_id || !s.label) return null;
  return `Your image looks like a ${s.label} — its preset is another good `
    + `starting point to compare.`;
}
