/**
 * Previous / next in the picture viewer (`ImageLightbox`).
 *
 * A page that opens the viewer from a grid of pictures (the Gallery, "My best
 * pictures") lets you step to the neighbouring picture without closing it, the
 * way every photo viewer does. These are the pure halves of that, kept out of
 * the component so they are testable without DOM pointer events.
 */

/** Where `current` sits in `items`, and its neighbours — or `null` when it is
 * not in the list (the list changed under an open viewer), in which case the
 * viewer simply shows no previous/next controls. The ends do not wrap: a
 * beginner flicking through ten pictures should feel the last one stop rather
 * than silently start again at the first. */
export function lightboxNeighbours<T>(
  items: readonly T[], current: T | null, same: (a: T, b: T) => boolean,
): { prev: T | null; next: T | null; position: string } | null {
  if (current == null || items.length < 2) return null;
  const i = items.findIndex((it) => same(it, current));
  if (i < 0) return null;
  return {
    prev: i > 0 ? items[i - 1] : null,
    next: i < items.length - 1 ? items[i + 1] : null,
    position: `${i + 1} of ${items.length}`,
  };
}

/** How far (px) a finger must travel sideways for a swipe to change picture. */
export const SWIPE_MIN_PX = 60;

/** A one-finger flick on an un-zoomed picture: −1 = previous (finger moved
 * right, as on a phone's photo app), +1 = next (moved left), 0 = not a swipe —
 * too short, or more up/down than sideways (a scroll or a sloppy tap must
 * never change the picture). */
export function swipeStep(dx: number, dy: number): -1 | 0 | 1 {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return 0;
  if (Math.abs(dx) < SWIPE_MIN_PX) return 0;
  if (Math.abs(dx) < 2 * Math.abs(dy)) return 0;
  return dx > 0 ? -1 : 1;
}

/** Whether a key press belongs to something else on the page (a text field,
 * an open download menu — Mantine's menus use the arrow keys to move between
 * items), in which case the viewer must not turn it into previous/next. */
export function keyBelongsElsewhere(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (target.closest("input, textarea, select, [contenteditable='true']")) return true;
  return target.closest(
    "[role='menu'], [role='menuitem'], [role='slider'], [aria-expanded='true']") != null;
}
