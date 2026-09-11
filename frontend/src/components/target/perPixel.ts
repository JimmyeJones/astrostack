/** What one *pixel* of a stack's canvas actually got — the denominator a
 * mosaic keeps breaking.
 *
 * Nearly everything a beginner is told about a finished stack is a claim about
 * a pixel: how clean it looks, whether it is "just one noisy sub", whether more
 * time still pays. On a single field the target's totals answer those directly,
 * because every sub covers the whole canvas — the run's frame count *is* the
 * depth, and its integration *is* the light one pixel received.
 *
 * A mosaic breaks that identity, and always in the flattering direction: its
 * subs are spread across the raster, so a target-wide number describes the
 * *sum* of the picture while the sentence about it describes a *part*. The
 * owner shoots 5×5, 10×10 and 12×8 rasters, where the gap is one to two orders
 * of magnitude — "3 h of light" on a 12×8 is under two minutes a panel. This
 * app has fixed the same substitution five times now (A2, A6, D1, the readiness
 * goal, and `auto_stack_min_frames`); this module is the one place the
 * correction lives for the surfaces that *report* it.
 *
 * The scale is `field_fulls` — how many single-frame field-fulls of sky the
 * run's own canvas covers, served per run by `webapp/field_fulls.py` (canvas
 * area ÷ one native frame's area, drizzle divided out). A single field is 1.0,
 * a 2×2 no-overlap mosaic 4.0, a 2×2 at 50 % overlap ~2.25.
 *
 * **It is a mean, and it is the conservative one.** Dividing by the canvas's
 * area gives the depth of an *evenly shot* raster; a mosaic with one deep panel
 * and eight thin ones has pixels on both sides of it. That is the right
 * trade for these surfaces, because the alternative — the peak — is the very
 * substitution this module exists to undo, and because a ragged union canvas
 * counts its uncovered corners as area, so the figure errs *shallow*: it warns
 * a little early rather than a little late. Where a run carries a *measured*
 * per-pixel depth (`grain_deep_frames`, read off the coverage map) that number
 * is better — but it is only populated on a mosaic uneven enough to have levels
 * to compare, so nothing can be built on it alone.
 */

/** The divisor to apply to a run's totals, from its served `field_fulls`.
 *
 * Anything missing, non-finite, or at or below 1.0 reads as **1.0** — i.e. no
 * correction, exactly the behaviour every one of these surfaces had before the
 * field existed, so an older backend (and every single-field target) is
 * bit-for-bit unchanged. Below 1.0 is clamped rather than honoured because a
 * scale under one would *inflate* the apparent depth, which is the direction
 * that hides the bug; the backend clamps identically and for the same reason.
 */
export function canvasFieldFulls(fieldFulls: number | null | undefined): number {
  return fieldFulls != null && Number.isFinite(fieldFulls) && fieldFulls > 1
    ? fieldFulls
    : 1;
}

/** True when this run's canvas covers materially more sky than one frame — i.e.
 * when a total and a per-pixel figure are different numbers and a sentence has
 * to say which one it means. */
export function spansMoreThanOneField(fieldFulls: number | null | undefined): boolean {
  return canvasFieldFulls(fieldFulls) > 1;
}

/** A run total (frames, or seconds of integration) as the share one pixel of its
 * canvas received. Identity on a single field. */
export function perPixel(total: number, fieldFulls: number | null | undefined): number {
  return total / canvasFieldFulls(fieldFulls);
}

/** "about 4 fields" / "about 2 fields" — how much sky the canvas spans, for a
 * sentence that has to explain why a total and a depth differ. Rounded to a
 * whole field: the precision is spurious (the canvas includes its uncovered
 * corners) and "about 4.3 fields of sky" reads as a measurement rather than the
 * rough scale it is. Never below 2, because this is only ever printed when the
 * canvas really does span more than one field. */
export function fieldsOfSkyLabel(fieldFulls: number | null | undefined): string {
  const fields = Math.max(2, Math.round(canvasFieldFulls(fieldFulls)));
  return `about ${fields} fields of sky`;
}
