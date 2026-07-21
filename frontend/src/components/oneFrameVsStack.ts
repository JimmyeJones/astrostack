/** Pure caption for the "one frame vs your stack" reveal.
 *
 * Turns the run's own provenance (a single sub's exposure + the stack's frame
 * count) into a plain-language line a beginner understands, e.g. "One 30-second
 * frame vs your 505-frame stack — stacking cut the noise and pulled out faint
 * detail." Every part is best-effort: a missing datum drops that clause rather
 * than printing a blank, so an older/edited run still reads cleanly. Kept pure so
 * a Vitest can pin every degraded shape without a DOM. */

/** Format a sub exposure in seconds as a compact human label ("30-second",
 * "2.5-second"). Returns null for a missing/non-finite/non-positive value. */
export function subExposureLabel(seconds: number | null | undefined): string | null {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  // Whole seconds read as "30-second"; a fractional exposure keeps one decimal.
  const rounded = Math.round(seconds * 10) / 10;
  const text = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  return `${text}-second`;
}

/** The caption sentence for the reveal. Degrades gracefully as fields drop:
 *  - both present → "One 30-second frame vs your 505-frame stack — …"
 *  - only frames  → "One frame vs your 505-frame stack — …"
 *  - neither      → "One frame vs your stack — …" */
export function oneFrameCaption(
  subExposureS: number | null | undefined,
  nFrames: number | null | undefined,
): string {
  const exp = subExposureLabel(subExposureS);
  const frame = exp ? `One ${exp} frame` : "One frame";
  const hasCount = nFrames != null && Number.isFinite(nFrames) && nFrames > 0;
  const stack = hasCount ? `your ${nFrames}-frame stack` : "your stack";
  return `${frame} vs ${stack} — stacking cut the noise and pulled out faint detail.`;
}
