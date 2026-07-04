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

/** Nudge point `i` by `(dx, dy)` (keyboard arrow-key access), clamped and
 * ordering-safe via {@link moveCurvePoint}. Endpoints keep their fixed x, so a
 * horizontal nudge on an endpoint is a no-op (only its y moves). Pure. */
export function nudgeCurvePoint(pts: Pt[], i: number, dx: number, dy: number): Pt[] {
  if (i < 0 || i >= pts.length) return pts.map((q) => [...q] as Pt);
  const [x, y] = pts[i];
  return moveCurvePoint(pts, i, [x + dx, y + dy]);
}

/** Remove interior point `i` (keyboard Delete access); endpoints are kept.
 * Returns a new list. Pure. */
export function removeCurvePoint(pts: Pt[], i: number): Pt[] {
  if (i <= 0 || i >= pts.length - 1) return pts.map((q) => [...q] as Pt);
  return pts.filter((_, j) => j !== i).map((q) => [...q] as Pt);
}

/** Add a point in the widest x-gap between existing points, at that gap's
 * x-midpoint with a y linearly interpolated from its two neighbours — so a
 * keyboard user (who can't click empty space) can still add a control point,
 * and it lands on the current curve (a no-op shape until they nudge it).
 * Returns the new x-sorted list and the index of the inserted point. Pure. */
export function addCurvePointInLargestGap(pts: Pt[]): { points: Pt[]; index: number } {
  const base = pts.length ? pts : ([[0, 0], [1, 1]] as Pt[]);
  if (base.length < 2) {
    const out = [...base, [1, 1]].sort((a, b) => a[0] - b[0]) as Pt[];
    return { points: out, index: out.length - 1 };
  }
  let gi = 0;
  let widest = -1;
  for (let j = 0; j < base.length - 1; j++) {
    const gap = base[j + 1][0] - base[j][0];
    if (gap > widest) { widest = gap; gi = j; }
  }
  const [x0, y0] = base[gi];
  const [x1, y1] = base[gi + 1];
  const mx = (x0 + x1) / 2;
  const my = y0 + (y1 - y0) * ((mx - x0) / (x1 - x0 || 1));
  const points = [...base.slice(0, gi + 1), [mx, my] as Pt, ...base.slice(gi + 1)];
  return { points, index: gi + 1 };
}
