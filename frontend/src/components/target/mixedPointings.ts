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
 *
 * The linkage is found with a **spatial grid**, not by testing every pair. The
 * original implementation compared all n(n−1)/2 pairs and called that "bounded
 * by the 2000-frame list cap" — a cap `api.listFrames` no longer has: it pages
 * until it holds every sub, deliberately, because truncating at 2,000 hid the
 * newest frames. So the bound the comment rested on was removed by a later fix
 * and nothing here noticed. Measured on this exact code: a single dithered
 * pointing costs **474 ms at 5,477 subs and 15.3 s at 35,894** — the two
 * deepest targets in the owner's library — synchronously, inside the `useMemo`
 * that renders the Target page and the Stack form, i.e. a frozen tab on the
 * page he opens every session, from a phone. The grid below is **the same
 * partition**, exhaustively pinned against the all-pairs version, at 3.2 ms.
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

// The cube grid the linkage scan below runs on. A unit vector's components are
// in [-1, 1] and CELL is ~0.0302, so an axis index lives in [-34, 33]; packing
// three of them into one integer key with a 512-wide field per axis leaves room
// for the ±CELL_REACH neighbour offsets without one axis ever carrying into the
// next, and a numeric key keeps the Map lookups cheap.
const CELL_AXIS = 512;
const CELL_HALF = 256;
// Cubes further apart than this on any axis are at least 2 cells apart, which
// is more than the link chord (CELL·√3), so they cannot hold a linking pair.
const CELL_REACH = 2;

function cellKey(ix: number, iy: number, iz: number): number {
  return (
    ((ix + CELL_HALF) * CELL_AXIS + (iy + CELL_HALF)) * CELL_AXIS + (iz + CELL_HALF)
  );
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
  // (dot ≥ cos(threshold)) share a cluster.
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

  // Bucket the unit vectors into a cube grid of side CELL, then link. Two rules
  // make this the *same* partition as testing every pair, not an approximation:
  //
  //  1. CELL is chosen so a cube's body diagonal is exactly the chord of
  //     LINK_DIST_DEG, so any two points sharing a cube are within the link
  //     distance **by construction** — they are unioned with no test at all.
  //     That is the case this exists for: a dithered pointing is arc-minutes
  //     wide, so all 35,894 of its subs fall in one cube.
  //  2. Two cubes offset by 3 or more indices on any axis are at least 2·CELL
  //     apart, which is further than the chord, so they can hold no linking
  //     pair. Only the ±2 neighbourhood is visited, and a pair of cubes already
  //     in one component is skipped entirely. Because rule 1 leaves every cube
  //     internally connected, the *first* linking pair found between two cubes
  //     merges both components whole — every later pair would repeat it — so
  //     the scan stops there.
  //
  // Worst case is still every pair of two neighbouring cubes that do not link;
  // best and typical case is linear. Measured above: 15.3 s → 3.2 ms.
  const CELL = (2 * Math.sin((LINK_DIST_DEG * Math.PI) / 360)) / Math.sqrt(3);
  const cells = new Map<number, number[]>();
  for (let i = 0; i < vecs.length; i++) {
    const key = cellKey(
      Math.floor(vecs[i][0] / CELL),
      Math.floor(vecs[i][1] / CELL),
      Math.floor(vecs[i][2] / CELL),
    );
    const bucket = cells.get(key);
    if (bucket) bucket.push(i);
    else cells.set(key, [i]);
  }
  // Rule 1 — everything in one cube is one component, untested.
  for (const idxs of cells.values()) {
    for (let k = 1; k < idxs.length; k++) parent[find(idxs[k])] = find(idxs[0]);
  }
  // Rule 2 — the ±2 neighbourhood, each unordered cube pair visited once.
  for (const [key, idxs] of cells) {
    for (let dx = -CELL_REACH; dx <= CELL_REACH; dx++) {
      for (let dy = -CELL_REACH; dy <= CELL_REACH; dy++) {
        for (let dz = -CELL_REACH; dz <= CELL_REACH; dz++) {
          if (dx === 0 && dy === 0 && dz === 0) continue;
          const other = key + (dx * CELL_AXIS + dy) * CELL_AXIS + dz;
          if (other < key) continue; // the neighbour will visit this pair
          const theirs = cells.get(other);
          if (!theirs) continue;
          if (find(idxs[0]) === find(theirs[0])) continue; // already one cluster
          let linked = false;
          for (let a = 0; a < idxs.length && !linked; a++) {
            const vi = vecs[idxs[a]];
            for (let b = 0; b < theirs.length; b++) {
              const vj = vecs[theirs[b]];
              if (vi[0] * vj[0] + vi[1] * vj[1] + vi[2] * vj[2] >= cosThresh) {
                parent[find(theirs[b])] = find(idxs[a]);
                linked = true;
                break;
              }
            }
          }
        }
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
