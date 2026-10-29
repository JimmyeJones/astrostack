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

import { notifications } from "@mantine/notifications";

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

/**
 * The hint once the server has said how big the file really is
 * (`api.stackFullResPngSize`). An unedited mosaic's download is trimmed of its
 * ragged border and an edited one carries its own crop, so the canvas printed by
 * {@link fullResPngHint} stopped being the file's size on exactly the pictures
 * this owner shoots. Without an answer (still loading, an older backend, or a
 * size the server won't promise) it is {@link fullResPngHint} unchanged.
 */
export function fullResDownloadHint(
  canvasW?: number | null, canvasH?: number | null,
  size?: { width: number | null; height: number | null; trimmed: boolean } | null,
): string {
  const w = size?.width, h = size?.height;
  if (!w || !h || w <= 0 || h <= 0) return fullResPngHint(canvasW, canvasH);
  if (size?.trimmed) return `Same look, ragged mosaic border trimmed (${w}×${h} px)`;
  // Smaller only because of the cap: the canvas sentence already says why.
  if (fullResPngCapped(canvasW, canvasH)) return fullResPngHint(canvasW, canvasH);
  return `Same look, full size (${w}×${h} px)`;
}

/** Canvas area (px) above which the full-res render is slow enough to need a
 *  word: measured at ~6 s for a 3494×2470 (8.6 MP) mosaic and ~25 s at
 *  5000×7000 on the agent container, slower on a NAS. An ordinary Seestar field
 *  (1080×1920, ~2 MP) comes back in about a second and gets no notice. */
export const FULL_RES_SLOW_PIXELS = 4_000_000;

/**
 * What to tell someone who just clicked "Full-res PNG" while the server
 * renders it — or `null` when the picture is small enough to arrive before a
 * notice could be read.
 *
 * A plain download link shows nothing in the browser until the first byte
 * arrives, so on a big mosaic the click looked like it did nothing for half a
 * minute; the owner reported it as taking "a super long time", and the natural
 * second click used to start a second render. Unknown dimensions answer with
 * the notice, because then the size really is unknown.
 */
export function fullResPreparingNotice(w?: number | null, h?: number | null): string | null {
  const known = !!w && !!h && w > 0 && h > 0;
  if (known && w * h < FULL_RES_SLOW_PIXELS) return null;
  const size = known ? `This picture is ${w}×${h} px, so it` : "A big picture";
  return `${size} can take a minute to prepare. The download starts by itself — `
    + "no need to click again. Downloading it a second time is instant.";
}

/** Show {@link fullResPreparingNotice} as a toast, for a download link's
 *  `onClick` (the link itself still does the download). One id, so a second
 *  click replaces the notice instead of stacking another. */
export function announceFullResDownload(w?: number | null, h?: number | null): void {
  const message = fullResPreparingNotice(w, h);
  if (!message) return;
  notifications.show({
    id: "full-res-preparing", title: "Preparing your full-size picture…",
    message, color: "blue", autoClose: 12000,
  });
}
