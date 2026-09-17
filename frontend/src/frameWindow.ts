/** How many of a target's subs the frames table actually puts in the DOM.
 *
 * The table rendered **one row per sub**, unconditionally: `list.map(...)` over
 * the complete frame list, which `api.listFrames` deliberately pages until it
 * has every row (the 2000-frame truncation bug is why it does). That is right
 * for the *data* — every badge, count and outlier test on the Target page is
 * computed over the whole list and must stay exact — and wrong for the *rows*.
 *
 * Measured on this page, in jsdom, with the real component: a frame row costs
 * **~22 DOM nodes** (icons, tooltips, badges, the accept control). So
 *
 * | subs  | nodes the table alone adds |
 * |-------|----------------------------|
 * |    20 |                        673 |
 * |   200 |                      4,633 |
 * | 2,000 |                     44,233 |
 *
 * and the owner's library — the one this app is for — holds a target with
 * **5,477** subs (the scale `webapp/estimate_cache.py` was measured at) and one
 * with **35,894**. Those are ~121,000 and ~790,000 nodes, in a table inside a
 * `mah="65vh"` scroll container that can show about twenty rows at a time, on a
 * page he opens from a phone. The page height never showed it — the container
 * caps that — which is why every dogfood page-height baseline passed.
 *
 * So the rows are windowed and the data is not. Nothing is removed (the owner's
 * one hard constraint): the window **grows as you scroll**, exactly as if every
 * row had always been there, and the last row carries a "show them all" button
 * so every sub stays reachable in one click even where an `IntersectionObserver`
 * is unavailable. Sorting is server-side, so "the worst frames" are still one
 * heading-tap away rather than at the bottom of a list nobody scrolls.
 */

/** Rows rendered up front, and added per growth step.
 *
 * ~20 rows fit the container, so 300 is about fifteen screens of scrolling
 * before the first growth — far past where anyone reads a row — for ~6,600
 * nodes, which is the cost of a 300-sub target today.
 */
export const FRAME_WINDOW_STEP = 300;

/** The next window size after a growth, never past the end of the list. */
export function growFrameWindow(
  shown: number,
  total: number,
  step: number = FRAME_WINDOW_STEP,
): number {
  return Math.min(total, Math.max(0, shown) + Math.max(1, step));
}

/** A window guaranteed to contain `index`, growing in whole steps.
 *
 * Keyboard grading (j/k) walks the **full** list, so it can select a frame the
 * window has not rendered yet — the selection would then highlight nothing and
 * the preview pane would show a frame with no row. Growing to cover the index
 * keeps the keyboard and the mouse looking at one table.
 */
export function frameWindowForIndex(
  shown: number,
  index: number,
  step: number = FRAME_WINDOW_STEP,
): number {
  if (index < shown) return shown;
  const steps = Math.ceil((index + 1) / Math.max(1, step));
  return Math.max(shown, steps * Math.max(1, step));
}

/** "Showing the first 300 of 5,477 subs." — or `null` when they are all shown.
 *
 * Says *first*, because the list is sorted and the window is its head: a reader
 * who wants the worst frames taps a column heading rather than scrolling to the
 * end. `null` is the ordinary case (almost every target is smaller than one
 * window), and it renders nothing at all — a row saying "showing all 12 of 12"
 * is one more line on a page the owner already calls busy.
 */
export function frameWindowNote(shown: number, total: number): string | null {
  if (shown >= total) return null;
  return `Showing the first ${shown.toLocaleString()} of ${total.toLocaleString()} subs.`;
}
