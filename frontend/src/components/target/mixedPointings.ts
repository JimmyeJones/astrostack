/** Pre-flight "this batch looks like two targets" guard.
 *
 * A Seestar's field of view is ~1.3° across; dithering nudges a pointing by
 * arc-minutes and a mosaic steps adjacent panels ~1° apart (they overlap), so
 * *one* target's solved frames — a single pointing, a dithered set, or a
 * contiguous mosaic — form a chain whose neighbours are all within a couple of
 * degrees. Two *different* targets accidentally dropped in one incoming folder
 * sit many degrees apart with nothing bridging the gap. If the user stacks such
 * a batch, the stacker picks one pointing as the reference and silently drops
 * every frame whose footprint doesn't overlap it (the NALIGNFL count) — so half
 * the night is wasted on a stack the user only discovers is half-complete
 * afterwards.
 *
 * We catch it *before* the stack by single-linkage-clustering the accepted,
 * solved pointings (exactly the frames that would be combined) at a 3° link
 * distance: a contiguous mosaic stays one cluster (each panel is <3° from the
 * next), but two well-separated targets fall into two clusters. Single-linkage
 * keys on the *gap between* groups, not their total span, so an arbitrarily
 * large but contiguous mosaic never trips it. We only flag when at least two
 * clusters are each substantial (≥ MIN_POINTING_FRAMES), so a lone mis-solved
 * frame — which the stack's own outlier rejection already handles — never nags.
 */
import type { Frame } from "../../api/client";

const LINK_DIST_DEG = 3.0;
const MIN_POINTING_FRAMES = 5;

export interface PointingCluster {
  count: number;
  raDeg: number;
  decDeg: number;
}

export interface MixedPointings {
  pointings: number; // number of substantial, well-separated pointings (≥2)
  majority: number; // frames in the largest pointing
  others: number; // frames in the other substantial pointings
  separationDeg: number; // separation between the two largest pointings
  // The accepted+solved frames that do NOT belong to the largest pointing —
  // exactly the subs the stacker would silently drop, and the ones a one-click
  // "reject the odd-target frames" should reject so only the majority pointing
  // remains. Includes any lone strays outside the majority too (they'd be
  // dropped anyway), so this count can exceed `others` (substantial-only).
  minorityIds: number[];
}

// Unit vector on the celestial sphere for an (RA, Dec) in degrees — lets us
// measure angular separation (and cluster) without any RA-wrap / pole special
// cases (a dot product is wrap-safe by construction).
function raDecToVec(raDeg: number, decDeg: number): [number, number, number] {
  const ra = (raDeg * Math.PI) / 180;
  const dec = (decDeg * Math.PI) / 180;
  const cd = Math.cos(dec);
  return [cd * Math.cos(ra), cd * Math.sin(ra), Math.sin(dec)];
}

function angularSepDeg(
  a: [number, number, number],
  b: [number, number, number],
): number {
  const dot = Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  return (Math.acos(dot) * 180) / Math.PI;
}

export function detectMixedPointings(frames: Frame[]): MixedPointings | null {
  const pts = frames.filter(
    (f) =>
      f.accept &&
      f.solved &&
      f.ra_center_deg !== null &&
      f.ra_center_deg !== undefined &&
      f.dec_center_deg !== null &&
      f.dec_center_deg !== undefined &&
      Number.isFinite(f.ra_center_deg) &&
      Number.isFinite(f.dec_center_deg),
  );
  // Too few to judge a bimodal split robustly (need two substantial groups).
  if (pts.length < 2 * MIN_POINTING_FRAMES) return null;

  const vecs = pts.map((f) =>
    raDecToVec(f.ra_center_deg as number, f.dec_center_deg as number),
  );
  const cosThresh = Math.cos((LINK_DIST_DEG * Math.PI) / 180);

  // Single-linkage clustering via union-find: two frames within LINK_DIST_DEG
  // (dot ≥ cos(threshold)) share a cluster. O(n²), bounded by the 2000-frame
  // list cap, and only recomputed when the frames data changes.
  const parent = pts.map((_, i) => i);
  const find = (i: number): number => {
    let r = i;
    while (parent[r] !== r) r = parent[r];
    while (parent[i] !== r) {
      const next = parent[i];
      parent[i] = r;
      i = next;
    }
    return r;
  };
  for (let i = 0; i < vecs.length; i++) {
    for (let j = i + 1; j < vecs.length; j++) {
      const vi = vecs[i];
      const vj = vecs[j];
      if (vi[0] * vj[0] + vi[1] * vj[1] + vi[2] * vj[2] >= cosThresh) {
        parent[find(j)] = find(i);
      }
    }
  }

  // Collect clusters as (count, summed unit vector) → centroid pointing, keyed
  // by union-find root so we can map the majority root back to its frames.
  const groups = new Map<number, { count: number; sum: [number, number, number] }>();
  for (let i = 0; i < vecs.length; i++) {
    const root = find(i);
    const g = groups.get(root) ?? { count: 0, sum: [0, 0, 0] as [number, number, number] };
    g.count += 1;
    g.sum[0] += vecs[i][0];
    g.sum[1] += vecs[i][1];
    g.sum[2] += vecs[i][2];
    groups.set(root, g);
  }

  const clusters: (PointingCluster & { vec: [number, number, number]; root: number })[] = [];
  for (const [root, g] of groups.entries()) {
    const [x, y, z] = g.sum;
    const norm = Math.hypot(x, y, z) || 1;
    const v: [number, number, number] = [x / norm, y / norm, z / norm];
    let ra = (Math.atan2(v[1], v[0]) * 180) / Math.PI;
    if (ra < 0) ra += 360;
    const dec = (Math.asin(Math.min(1, Math.max(-1, v[2]))) * 180) / Math.PI;
    clusters.push({ count: g.count, raDeg: ra, decDeg: dec, vec: v, root });
  }
  clusters.sort((a, b) => b.count - a.count);

  // Only a *clearly* bimodal set warns: at least two substantial pointings.
  const substantial = clusters.filter((c) => c.count >= MIN_POINTING_FRAMES);
  if (substantial.length < 2) return null;

  const majority = substantial[0].count;
  const others = substantial.slice(1).reduce((s, c) => s + c.count, 0);
  const separationDeg = angularSepDeg(substantial[0].vec, substantial[1].vec);

  // Every accepted+solved frame outside the largest pointing — the subs the
  // stacker would drop, and the ones a one-click "reject the odd frames" clears
  // so only the majority pointing (the reference) is left to stack.
  const majorityRoot = substantial[0].root;
  const minorityIds: number[] = [];
  for (let i = 0; i < pts.length; i++) {
    if (find(i) !== majorityRoot) minorityIds.push(pts[i].id);
  }

  return { pointings: substantial.length, majority, others, separationDeg, minorityIds };
}
