/**
 * What the "Full-res PNG" download actually hands over.
 *
 * Four screens offer this file, and until v0.309.1 all four described it as the
 * picture at **native size** — the Target page and the Dashboard strip said
 * "(native size)", History went further and printed the exact canvas dimensions
 * ("Same look, full size (12000×9000 px)"). The endpoint behind it decimates
 * anything whose long edge exceeds {@link FULL_RES_PNG_MAX_LONG_EDGE}, a
 * deliberate ceiling that bounds the render's memory and the response size on a
 * RAM-capped NAS. So on exactly the pictures where the difference matters — a
 * union mosaic, the thing this owner shoots — the copy promised pixels the file
 * does not contain, and History quoted a number the download demonstrably
 * misses.
 *
 * Nothing is wrong with the *cap*: the FITS and the TIFF beside it hold the true
 * native pixels, and that is what they are for. What was wrong was the sentence.
 * These helpers are the one place that sentence is written, so the four surfaces
 * cannot drift into four different claims about one file.
 *
 * ⚠ **`FULL_RES_PNG_MAX_LONG_EDGE` is mirrored by hand** from
 * `webapp/routers/stack.py`'s `_FULL_RES_PNG_MAX_LONG_EDGE` — change them
 * together. `tests/test_fullres_cap_mirror.py` fails if they drift, because a
 * silently-stale copy here would put the untruth straight back.
 */

/** The long-edge ceiling the full-res PNG endpoint renders to. Mirrors
 *  `webapp/routers/stack.py:_FULL_RES_PNG_MAX_LONG_EDGE`. */
export const FULL_RES_PNG_MAX_LONG_EDGE = 8000;

/** Does this canvas come back decimated rather than native?
 *
 *  Unknown dimensions (a surface that doesn't carry them, or a run row from a
 *  build that didn't) answer `false` — i.e. word it the way the overwhelmingly
 *  common case is true, rather than warning about a cap that probably isn't
 *  being hit. */
export function fullResPngCapped(w?: number | null, h?: number | null): boolean {
  if (!w || !h || w <= 0 || h <= 0) return false;
  return Math.max(w, h) > FULL_RES_PNG_MAX_LONG_EDGE;
}

/**
 * The menu-item label for the full-res download.
 *
 * Unchanged for every canvas that really does come back native — the point is
 * not to hedge everywhere, it is to stop claiming "native size" on the one kind
 * of picture where it is false.
 */
export function fullResPngLabel(w?: number | null, h?: number | null): string {
  return fullResPngCapped(w, h)
    ? `Full-res PNG (up to ${FULL_RES_PNG_MAX_LONG_EDGE} px)`
    : "Full-res PNG (native size)";
}

/**
 * The dimmed one-line hint under that item, where a surface has room for one
 * (History's artifact menu).
 *
 * When the picture is capped it names the canvas it was capped *from* and points
 * at the two files that do hold those pixels, so "why is my download smaller
 * than the number you printed?" never has to be asked.
 */
export function fullResPngHint(w?: number | null, h?: number | null): string {
  if (!w || !h || w <= 0 || h <= 0) return "Same look, full size";
  if (!fullResPngCapped(w, h)) return `Same look, full size (${w}×${h} px)`;
  return `Same look, up to ${FULL_RES_PNG_MAX_LONG_EDGE} px — this canvas is `
    + `${w}×${h}, so the FITS or TIFF holds its native pixels`;
}
