/** How many subs actually landed on **one pixel** — the denominator the Stack
 * form's cautions are really about, before the button is pressed.
 *
 * Every caution on that form is a statement about a pixel's *sample* count:
 * drizzle needs enough dither-phased samples to fill a finer grid (the engine
 * recommends 200+, and `drizzle_path.py` counts them "per output pixel"); κ-σ
 * estimates each pixel's spread across the frames that hit it; a min/max trim
 * of k needs `2k+1` frames **per pixel** to fully apply. On a single field the
 * target's frame count answers all three directly — every sub covers every
 * pixel, so the total *is* the depth.
 *
 * A mosaic breaks that identity in the flattering direction: the subs are
 * spread across the raster, so the total describes the *sum* of the picture
 * while the sentence about it describes a *part*. On a 3×3 raster 225 subs deep
 * in total, a pixel has seen about 25 — an order of magnitude below what the
 * copy quoting 225 implies. The app has now corrected this substitution on the
 * method picker (`auto_reject`), on the reach answer (`rejection_reach`), on the
 * walk-away floor (`auto_stack_min_frames`) and on the Target page's coaching
 * (`perPixel.ts`); this module is the correction for the *pre-run* form, where
 * the exact number is available rather than estimated from canvas area.
 *
 * The depth is `stack-estimate`'s `panel_depth` — the thinnest substantial
 * panel, `seestack.stack.stacker.auto_reject_depth`. Deliberately the **same**
 * number the rejection answers on that response are computed from, rather than
 * a second definition: a form that warned from one depth while naming a method
 * chosen from another is exactly the drift these fixes keep undoing.
 */

/** Below this many samples **on one pixel**, drizzle is the wrong advice — it
 * spreads each sub across a finer grid and needs enough dither-phased samples
 * to fill it, so this thin it comes back slower, noisier and gappier than the
 * ordinary weighted-mean path.
 *
 * Hand-mirrored from `seestack.stack.drizzle_path.DRIZZLE_MIN_SAMPLES_PER_PIXEL`
 * (a TS module cannot import a Python constant — the `fullres.ts` arrangement),
 * and guarded against drift by `tests/test_drizzle_bar_mirror.py`. It lives
 * here, beside `samplesPerPixel`, because the bar is meaningless without the
 * denominator: every surface that quotes it must compare it against a *pixel's*
 * count, never a mosaic's frame total.
 */
export const DRIZZLE_MIN_SAMPLES_PER_PIXEL = 100;

/** The honest sample count for one pixel: the mosaic's panel depth where there
 * is one, the target's frame count otherwise.
 *
 * `null`/missing/non-finite/non-positive all read as "no correction" — which is
 * both the single-field answer and, byte for byte, the behaviour every caller
 * had before the field was served, so an older backend is unaffected. Clamped
 * at the frame count because a depth above the total is not a thing a canvas
 * can have, and the direction that inflates depth is the one that hides the bug.
 */
export function samplesPerPixel(
  nFrames: number,
  panelDepth: number | null | undefined,
): number {
  if (panelDepth == null || !Number.isFinite(panelDepth) || panelDepth <= 0) {
    return nFrames;
  }
  return Math.min(Math.floor(panelDepth), nFrames);
}

/** True when a total and a per-pixel figure are different numbers here, so a
 * sentence has to say which one it means. */
export function spreadAcrossPanels(
  nFrames: number,
  panelDepth: number | null | undefined,
): boolean {
  return samplesPerPixel(nFrames, panelDepth) < nFrames;
}

/** The count, worded so a beginner can see *which* number it is.
 *
 * A single field keeps today's wording exactly ("250 accepted, solved frames").
 * A mosaic says the depth first, because that is what the caution is about, and
 * carries the total in parentheses so the sentence never looks like the app has
 * lost frames the Frames table plainly shows.
 */
export function samplesPerPixelPhrase(
  nFrames: number,
  panelDepth: number | null | undefined,
): string {
  const depth = samplesPerPixel(nFrames, panelDepth);
  if (depth === nFrames) {
    return `${nFrames} accepted, solved frame${nFrames === 1 ? "" : "s"}`;
  }
  return `about ${depth} sub${depth === 1 ? "" : "s"} on each patch of sky`
    + ` (${nFrames} in total, spread across the mosaic)`;
}
