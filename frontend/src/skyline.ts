// "Draw your skyline" — the geometry behind the visual horizon editor.
//
// The Tonight planner already knows how to skip a target while it's behind your
// trees: `HorizonProfile` (seestack/nightplan.py) takes an [[azimuth, minimum
// clear altitude], …] list and linear-interpolates between the points, wrapping
// around 360°. Setting it, though, meant typing compass bearings — and a
// backyard Seestar owner knows "the big tree is over there", not "az 95°".
//
// This module is the pure half of the drag-a-skyline control: sampling an
// existing profile onto evenly-spaced buckets, painting a drag across them, and
// turning them back into the exact array the backend already consumes. Kept
// separate from the component so the arithmetic that decides what the planner
// will believe is directly testable.

export type HorizonPoint = [number, number];

/** Azimuth spacing of the drawn skyline, in degrees. 15° gives 24 buckets —
 *  fine enough to draw a single tree, coarse enough to sweep in one gesture. */
export const SKYLINE_AZ_STEP = 15;
export const SKYLINE_BUCKETS = 360 / SKYLINE_AZ_STEP;
/** Tallest obstruction the strip can draw. Nothing in a backyard blocks 60° of
 *  sky; the numeric editor still accepts up to 90° for the rare case. */
export const SKYLINE_MAX_ALT = 60;

/** The azimuth each bucket stands for: 0, 15, 30 … 345. */
export function bucketAzimuths(): number[] {
  return Array.from({ length: SKYLINE_BUCKETS }, (_, i) => i * SKYLINE_AZ_STEP);
}

function wrap360(az: number): number {
  const a = az % 360;
  return a < 0 ? a + 360 : a;
}

export function clampAltitude(alt: number): number {
  if (!Number.isFinite(alt)) return 0;
  return Math.max(0, Math.min(SKYLINE_MAX_ALT, alt));
}

/**
 * The obstruction altitude an existing profile reports at one azimuth.
 *
 * Mirrors `HorizonProfile.altitude_at` — linear interpolation between the
 * sorted points, wrapping through the 350°→10° seam — so what the strip draws
 * is what the planner will actually use. An empty profile is an open horizon.
 */
export function altitudeAtAz(points: HorizonPoint[], az: number): number {
  const clean = (Array.isArray(points) ? points : [])
    .filter((p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]))
    .map((p) => [wrap360(Number(p[0])), clampAltitude(Number(p[1]))] as HorizonPoint)
    .sort((a, b) => a[0] - b[0]);
  if (clean.length === 0) return 0;
  if (clean.length === 1) return clean[0][1];

  const target = wrap360(az);
  for (let i = 0; i < clean.length - 1; i += 1) {
    const [a0, h0] = clean[i];
    const [a1, h1] = clean[i + 1];
    if (target >= a0 && target <= a1) {
      const span = a1 - a0;
      return span === 0 ? h1 : h0 + ((h1 - h0) * (target - a0)) / span;
    }
  }
  // Past the last point (or before the first): interpolate across the seam.
  const [aLast, hLast] = clean[clean.length - 1];
  const [aFirst, hFirst] = clean[0];
  const span = 360 - aLast + aFirst;
  if (span === 0) return hLast;
  const along = target >= aLast ? target - aLast : 360 - aLast + target;
  return hLast + ((hFirst - hLast) * along) / span;
}

/** Sample a saved profile onto the drawing buckets, for display. */
export function profileToHeights(points: HorizonPoint[]): number[] {
  return bucketAzimuths().map((az) => clampAltitude(altitudeAtAz(points, az)));
}

/**
 * Turn drawn buckets back into the profile the backend stores.
 *
 * A skyline the user has flattened everywhere emits `[]`, not 24 zeros: an
 * empty profile is what an install that never touched this feature has, so
 * "clear it" restores today's behaviour exactly rather than persisting a mask
 * that happens to block nothing.
 *
 * Otherwise **every** bucket is emitted, zeros included. A zero is real
 * information — "the sky is open here" — and dropping it would let the
 * backend's interpolation bridge straight across the gap and invent an
 * obstruction between two trees.
 */
export function heightsToProfile(heights: number[]): HorizonPoint[] {
  const clamped = heights.map(clampAltitude);
  if (clamped.every((h) => h <= 0)) return [];
  return bucketAzimuths().map((az, i) => [az, Math.round(clamped[i])] as HorizonPoint);
}

/** Bucket index nearest an azimuth (wrapping). */
export function nearestBucket(az: number): number {
  return Math.round(wrap360(az) / SKYLINE_AZ_STEP) % SKYLINE_BUCKETS;
}

/**
 * Paint one drag segment onto the buckets.
 *
 * A pointer move reports where the finger *is*, not every bucket it crossed, so
 * a quick sweep would otherwise leave the buckets in between untouched. Walk
 * the shorter way round from the previous sample to this one and interpolate,
 * so one gesture draws a continuous skyline. Returns a new array.
 */
export function paintSpan(
  heights: number[], fromAz: number, fromAlt: number, toAz: number, toAlt: number,
): number[] {
  const next = heights.slice();
  const a0 = clampAltitude(fromAlt);
  const a1 = clampAltitude(toAlt);
  const start = nearestBucket(fromAz);
  const end = nearestBucket(toAz);

  // Steps the short way round; equal buckets paint just the one.
  const forward = (end - start + SKYLINE_BUCKETS) % SKYLINE_BUCKETS;
  const backward = (start - end + SKYLINE_BUCKETS) % SKYLINE_BUCKETS;
  const steps = Math.min(forward, backward);
  const dir = forward <= backward ? 1 : -1;

  if (steps === 0) {
    next[start] = a1;
    return next;
  }
  for (let s = 0; s <= steps; s += 1) {
    const idx = (((start + dir * s) % SKYLINE_BUCKETS) + SKYLINE_BUCKETS) % SKYLINE_BUCKETS;
    next[idx] = a0 + ((a1 - a0) * s) / steps;
  }
  return next;
}

/** An all-open skyline — the same thing as no profile at all. */
export function emptyHeights(): number[] {
  return new Array(SKYLINE_BUCKETS).fill(0);
}

/**
 * Coarse starting points, so nobody faces a blank strip.
 *
 * Deliberately vague — these are a first approximation the user then drags into
 * shape, not a claim about their garden. Each is expressed as a function of the
 * bucket's azimuth so the shapes stay readable.
 */
export const SKYLINE_PRESETS: {
  id: string; label: string; hint: string; heights: () => number[];
}[] = [
  {
    id: "open",
    label: "Open sky",
    hint: "Nothing blocking — a field, a flat roof, the coast.",
    heights: emptyHeights,
  },
  {
    id: "suburban",
    label: "Suburban garden",
    hint: "Fences, hedges and rooftops all round.",
    heights: () => bucketAzimuths().map(() => 12),
  },
  {
    id: "house-south",
    label: "Building to the south",
    hint: "A house or wall blocking the southern sky.",
    heights: () => bucketAzimuths().map((az) => (arcContains(az, 135, 225) ? 32 : 8)),
  },
  {
    id: "trees-north",
    label: "Trees to the north",
    hint: "A treeline along the northern horizon.",
    heights: () => bucketAzimuths().map((az) => (arcContains(az, 315, 45) ? 26 : 6)),
  },
];

/** Whether an azimuth lies on the arc from `from` to `to`, going clockwise. */
export function arcContains(az: number, from: number, to: number): boolean {
  const a = wrap360(az);
  const f = wrap360(from);
  const t = wrap360(to);
  return f <= t ? a >= f && a <= t : a >= f || a <= t;
}

// ---- Strip geometry (shared by the renderer and its tests) ----------------
// A fixed 720×210 viewBox scaled to whatever width the card gets, so the
// compass labels stay legible instead of stretching with the panorama.
export const STRIP = {
  w: 720, h: 210, x0: 34, x1: 704, yTop: 12, yBase: 172,
} as const;

export function xAtAz(az: number): number {
  return STRIP.x0 + (wrap360(az) / 360) * (STRIP.x1 - STRIP.x0);
}

export function yAtAlt(alt: number): number {
  const f = clampAltitude(alt) / SKYLINE_MAX_ALT;
  return STRIP.yBase - f * (STRIP.yBase - STRIP.yTop);
}

/** Inverse of {@link xAtAz}: the azimuth a click at this viewBox x means. */
export function azAtX(x: number): number {
  return wrap360(((x - STRIP.x0) / (STRIP.x1 - STRIP.x0)) * 360);
}

/** Inverse of {@link yAtAlt}, clamped to the drawable range. */
export function altAtY(y: number): number {
  const f = (STRIP.yBase - y) / (STRIP.yBase - STRIP.yTop);
  return clampAltitude(f * SKYLINE_MAX_ALT);
}

/**
 * The filled-ground polygon for a set of drawn heights.
 *
 * Drawn as straight segments between bucket centres — the same linear
 * interpolation the planner does — so the picture is an honest preview of what
 * will actually be blocked, not a prettier curve. Both ends are pinned to
 * bucket 0 so the shape closes across the northern seam.
 */
export function groundPolygonPoints(heights: number[]): string {
  const hs = heights.length ? heights : emptyHeights();
  const at = (x: number, y: number) => `${x.toFixed(1)},${y.toFixed(1)}`;
  const pts: string[] = [at(STRIP.x0, STRIP.yBase), at(STRIP.x0, yAtAlt(hs[0]))];
  bucketAzimuths().forEach((az, i) => {
    if (i === 0) return;
    pts.push(at(xAtAz(az), yAtAlt(hs[i])));
  });
  pts.push(at(STRIP.x1, yAtAlt(hs[0])), at(STRIP.x1, STRIP.yBase));
  return pts.join(" ");
}

/** A one-line plain-language summary of what the drawn skyline blocks. */
export function describeSkyline(heights: number[]): string {
  // Sanitise in place rather than filtering: the index has to keep meaning a
  // bucket, or the bearing named below belongs to a different part of the sky.
  const hs = heights.map((h) => (Number.isFinite(h) ? h : 0));
  if (!hs.length || hs.every((h) => h <= 0)) {
    return "Open horizon — the planner counts a target from the moment it clears your minimum altitude.";
  }
  const tallest = Math.max(...hs);
  const worst = bucketAzimuths()[hs.indexOf(tallest)];
  const blocked = hs.filter((h) => h > 0).length;
  const share = Math.round((blocked / SKYLINE_BUCKETS) * 100);
  return `Blocking up to ${Math.round(tallest)}° towards ${compassLabel(worst)}, `
    + `over about ${share}% of the compass.`;
}

/** Coarse compass name for a bearing — the strip's own labels. */
export function compassLabel(az: number): string {
  const names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return names[Math.round(wrap360(az) / 45) % 8];
}
