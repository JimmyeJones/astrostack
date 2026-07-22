/** Honest "thin stack" warning — a stack that combined very few frames.
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
 * Returns `null` for a healthy frame count (no nag), otherwise a level +
 * message. `level` lets the UI pick colour/urgency: "single" (1 frame — not
 * really a stack) vs "thin" (2–4 — very few).
 */

// At/under this many combined frames the result is genuinely noisy and worth a
// heads-up. Chosen from the √N noise curve: below ~5 frames the stack has barely
// started averaging the sky down.
export const THIN_STACK_MAX_FRAMES = 4;

export interface ThinStackWarning {
  level: "single" | "thin";
  frames: number;
  message: string;
}

export function thinStackWarning(
  nFramesUsed: number | null | undefined,
): ThinStackWarning | null {
  // Unknown / not-yet-stacked → nothing to warn about.
  if (nFramesUsed == null || !Number.isFinite(nFramesUsed) || nFramesUsed < 0) {
    return null;
  }
  if (nFramesUsed > THIN_STACK_MAX_FRAMES) return null;

  const next =
    "Check that your subs plate-solved and weren't over-rejected (see the " +
    '"rejected" count above), then add more subs — a stack only gets cleaner as ' +
    "it combines more frames.";

  if (nFramesUsed <= 1) {
    return {
      level: "single",
      frames: nFramesUsed,
      message:
        `This stack combined only ${nFramesUsed} frame — that's a single sub, ` +
        "not a stack, so it will look noisy and speckled. " + next,
    };
  }
  return {
    level: "thin",
    frames: nFramesUsed,
    message:
      `This stack combined only ${nFramesUsed} frames — very few, so it will ` +
      "still look noisy. " + next,
  };
}
