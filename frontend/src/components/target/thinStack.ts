/** Honest "thin stack" warning — a stack whose picture is only a few subs deep.
 *
 * A stack only smooths noise as it combines more subs: measured on synthetic
 * faint-star fields the background noise falls ~√N (1→4 frames ≈ 2× cleaner,
 * 4→16 ≈ 2× again). So a "stack" of 1 frame is just one raw sub — it comes out
 * as per-pixel colour speckle ("gibberish"), exactly what a beginner sees when a
 * faint/sparse-star field loses most of its subs to plate-solve failure or
 * over-aggressive auto-reject. Rather than present that noisy result as a
 * finished picture with no explanation, surface a plain-language heads-up with a
 * concrete next step. Pure + threshold-driven so it's trivially unit-tested.
 *
 * **The threshold is a depth, not a count** (corrected 2026-09-11). "√N has
 * barely started averaging the sky down" is a claim about one pixel, and on a
 * mosaic the run's frame count is not that: nine subs over a 3×3 raster is one
 * sub everywhere, and it rendered as exactly the speckle this warning exists for
 * while the warning stayed silent because 9 > 4. That is the same substitution
 * `auto_stack_min_frames` was fixed for in v0.415.0 — which now *holds such a
 * mosaic back* rather than publishing it, so the two surfaces disagreed about
 * one picture. The depth comes from the run's own `field_fulls` (see
 * `perPixel.ts`); a single field is unchanged in every respect, wording
 * included.
 *
 * Returns `null` for a healthy depth (no nag), otherwise a level + message.
 * `level` lets the UI pick colour/urgency: "single" (one sub deep — not really a
 * stack) vs "thin" (2–4 — very few).
 */

import { fieldsOfSkyLabel, perPixel, spansMoreThanOneField } from "./perPixel";

// At/under this many subs *on one part of the picture* the result is genuinely
// noisy and worth a heads-up. Chosen from the √N noise curve: below ~5 frames
// the stack has barely started averaging the sky down.
export const THIN_STACK_MAX_FRAMES = 4;

export interface ThinStackWarning {
  level: "single" | "thin";
  /** Subs on one part of the picture — the run's frame count on a single field,
   *  and its per-pixel depth on a mosaic. The number the message is about. */
  frames: number;
  message: string;
}

export function thinStackWarning(
  nFramesUsed: number | null | undefined,
  /** How many single-frame field-fulls of sky the run's canvas covers
   * (`StackRun.field_fulls`). Omit / null / ≤1 on a single field and on any
   * surface that doesn't have the figure — the warning is then exactly what it
   * has always been. */
  fieldFulls?: number | null,
): ThinStackWarning | null {
  // Unknown / not-yet-stacked → nothing to warn about.
  if (nFramesUsed == null || !Number.isFinite(nFramesUsed) || nFramesUsed < 0) {
    return null;
  }
  const mosaic = spansMoreThanOneField(fieldFulls);
  // Round the depth so the sentence and the test agree on one integer; a mean
  // depth of 4.6 is "about 5 subs", not a fifth of a sub short of the bar.
  const depth = mosaic
    ? Math.round(perPixel(nFramesUsed, fieldFulls))
    : nFramesUsed;
  if (depth > THIN_STACK_MAX_FRAMES) return null;

  const next =
    "Check that your subs plate-solved and weren't over-rejected (see the " +
    '"rejected" count above), then add more subs — a stack only gets cleaner as ' +
    "it combines more frames.";

  if (mosaic) {
    // Name both figures. A mosaic owner reading "only 3 subs" under a picture
    // the same page says took 27 has been told two things that can't both be
    // true; the spread is the fact that reconciles them.
    const spread =
      `Your ${nFramesUsed} subs are spread across ${fieldsOfSkyLabel(fieldFulls)}, ` +
      `so each part of this picture has only about ${depth} ` +
      `${depth === 1 ? "sub" : "subs"} on it`;
    if (depth <= 1) {
      return {
        level: "single",
        frames: depth,
        message:
          `${spread} — a single sub, not a stack, so it will look noisy and ` +
          `speckled. ${next}`,
      };
    }
    return {
      level: "thin",
      frames: depth,
      message: `${spread} — very few, so it will still look noisy. ${next}`,
    };
  }

  if (depth <= 1) {
    return {
      level: "single",
      frames: depth,
      message:
        `This stack combined only ${depth} frame — that's a single sub, ` +
        "not a stack, so it will look noisy and speckled. " + next,
    };
  }
  return {
    level: "thin",
    frames: depth,
    message:
      `This stack combined only ${depth} frames — very few, so it will ` +
      "still look noisy. " + next,
  };
}
