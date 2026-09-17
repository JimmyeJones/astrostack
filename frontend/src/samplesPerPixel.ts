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
 * (`perPixel.ts`); this module is the correction for the *pre-run* form, from
 * the canvas the run has not made yet — the same area arithmetic `perPixel.ts`
 * does after the fact, on a canvas the estimate has already sized.
 *
 * The depth is `stack-estimate`'s **`pixel_depth`** — canvas area ÷ frame
 * footprint, i.e. `webapp.field_fulls.field_fulls_of_sky`, the same measure four
 * other surfaces already use to answer "how deep is a pixel of this run?".
 *
 * It used to be that response's `panel_depth` (the thinnest substantial pointing
 * cluster, `seestack.stack.stacker.auto_reject_depth`), on the reasoning that a
 * form warning from one depth while naming a method chosen from another is the
 * drift these fixes keep undoing. That reasoning was right about *method
 * selection* and wrong about *sentences*, and the two are different questions:
 *
 * * "can this rejection bite **anywhere**?" is about the thinnest part of the
 *   raster, and `panel_depth` is exactly that number — it still drives
 *   `rejection_reach` and `_resolve_auto_reject`, untouched;
 * * "how many subs are on **each patch of sky**?" is about a *typical* pixel,
 *   and the thinnest cluster is not it. `PANEL_LINK_DIST_DEG` is 0.25°, about a
 *   fifth of a Seestar frame's short side, so heavily overlapping pointings are
 *   labelled *different* clusters and a pixel is covered by many clusters'
 *   frames at once.
 *
 * Measured against the owner's own coverage maps, `panel_depth` came out ~0.10×
 * the real per-pixel depth on 12 of 17 mosaics — and on one target it went the
 * *other* way, so the error was not even reliably conservative. Six drizzle runs
 * were told to "turn Drizzle off" on pictures measured 117–153 subs deep, above
 * the engine's own 100-sample bar (observer issue #901).
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

/** The honest sample count for one pixel: the canvas's per-pixel depth where
 * there is one, the target's frame count otherwise.
 *
 * `null`/missing/non-finite/non-positive all read as "no correction" — which is
 * both the single-field answer and, byte for byte, the behaviour every caller
 * had before the field was served, so an older backend is unaffected. Clamped
 * at the frame count because a depth above the total is not a thing a canvas
 * can have, and the direction that inflates depth is the one that hides the bug.
 *
 * Callers pass `pixel_depth ?? panel_depth`: the canvas measure when the
 * backend serves one (every union-canvas mosaic), and the old thinnest-cluster
 * number otherwise — an older backend, or a mosaic forced onto the reference
 * canvas, where area arithmetic has nothing to say and today's answer stands.
 */
export function samplesPerPixel(
  nFrames: number,
  depth: number | null | undefined,
): number {
  if (depth == null || !Number.isFinite(depth) || depth <= 0) {
    return nFrames;
  }
  return Math.min(Math.floor(depth), nFrames);
}

/** True when a total and a per-pixel figure are different numbers here, so a
 * sentence has to say which one it means. */
export function spreadAcrossPanels(
  nFrames: number,
  depth: number | null | undefined,
): boolean {
  return samplesPerPixel(nFrames, depth) < nFrames;
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
  canvasDepth: number | null | undefined,
): string {
  const depth = samplesPerPixel(nFrames, canvasDepth);
  if (depth === nFrames) {
    return `${nFrames} accepted, solved frame${nFrames === 1 ? "" : "s"}`;
  }
  return `about ${depth} sub${depth === 1 ? "" : "s"} on each patch of sky`
    + ` (${nFrames} in total, spread across the mosaic)`;
}
