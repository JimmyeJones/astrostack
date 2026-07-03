/** Pure geometry for dragging a point in the tone-curve editor.
 *
 * The widget kept the dragged point's index fixed but re-sorted the point list
 * by x on every move, so once a dragged interior point crossed a neighbour's x
 * the index silently started addressing the *other* point — the drag "jumped"
 * to a different handle. Clamping an interior point's x to stay strictly between
 * its neighbours keeps the sort order stable, so the index never goes stale and
 * points can't cross. Endpoints keep their fixed x (0 and 1). */

export type Pt = [number, number];

/** Minimum x gap kept between adjacent points so a drag can't collapse or cross
 * two handles onto the same x. */
export const MIN_GAP = 1e-3;

/** Move point `i` to `p`, returning the new (still x-sorted) point list.
 * Endpoints keep x=0 / x=1; interior points are clamped between their
 * neighbours so ordering — and therefore `i` — stays valid. */
export function moveCurvePoint(pts: Pt[], i: number, p: Pt): Pt[] {
  if (i < 0 || i >= pts.length) return pts.map((q) => [...q] as Pt);
  const y = Math.min(1, Math.max(0, p[1]));
  let x = Math.min(1, Math.max(0, p[0]));
  if (i === 0) {
    x = 0;
  } else if (i === pts.length - 1) {
    x = 1;
  } else {
    const lo = pts[i - 1][0] + MIN_GAP;
    const hi = pts[i + 1][0] - MIN_GAP;
    // If the neighbours are already tighter than 2·MIN_GAP, sit at their midpoint
    // rather than inverting the clamp.
    x = lo <= hi ? Math.min(hi, Math.max(lo, x)) : (pts[i - 1][0] + pts[i + 1][0]) / 2;
  }
  return pts.map((q, j) => (j === i ? ([x, y] as Pt) : ([...q] as Pt)));
}
