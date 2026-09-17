import { describe, expect, it } from "vitest";
import { detectMixedPointings } from "./mixedPointings";
import type { Frame } from "../../api/client";

function mkFrame(id: number, overrides: Partial<Frame> = {}): Frame {
  return {
    id, name: `f${id}.fits`, timestamp_utc: "2026-01-01T00:00:00",
    exposure_s: 30, gain: 100, width_px: 480, height_px: 320,
    bayer_pattern: "RGGB", solved: true, ra_center_deg: 10, dec_center_deg: 20,
    ra_hint_deg: null, dec_hint_deg: null, fwhm_px: 2.5, star_count: 100,
    sky_adu_median: 500, eccentricity_median: 0.4, transparency_score: 5000,
    streak_detected: false,
    accept: true, reject_reason: null, user_override: false, ...overrides,
  };
}

// n solved+accepted frames scattered within ~jitter degrees of (ra, dec).
function cluster(
  n: number,
  ra: number,
  dec: number,
  startId: number,
  jitter = 0.3,
  over: Partial<Frame> = {},
): Frame[] {
  return Array.from({ length: n }, (_, i) =>
    mkFrame(startId + i, {
      ra_center_deg: ra + ((i % 3) - 1) * jitter,
      dec_center_deg: dec + ((i % 2) - 0.5) * jitter,
      ...over,
    }),
  );
}

describe("detectMixedPointings", () => {
  it("is null for a single dithered pointing", () => {
    expect(detectMixedPointings(cluster(20, 83, -5, 1))).toBeNull();
  });

  it("is null for a contiguous mosaic (adjacent panels ~1° apart)", () => {
    // A 3×3 Seestar mosaic: panels step ~1° and overlap, so single-linkage at 3°
    // keeps the whole thing one cluster even though its total span is ~2.4°.
    const panels: Frame[] = [];
    let id = 1;
    for (let px = 0; px < 3; px++) {
      for (let py = 0; py < 3; py++) {
        panels.push(...cluster(4, 40 + px * 1.2, 30 + py * 1.2, id, 0.1));
        id += 4;
      }
    }
    expect(detectMixedPointings(panels)).toBeNull();
  });

  it("flags two well-separated targets in one folder", () => {
    const frames = [...cluster(18, 10, 20, 1), ...cluster(12, 83, -5, 100)];
    const res = detectMixedPointings(frames);
    expect(res).not.toBeNull();
    expect(res!.pointings).toBe(2);
    expect(res!.majority).toBe(18);
    expect(res!.others).toBe(12);
    expect(res!.separationDeg).toBeGreaterThan(30);
  });

  it("returns the minority frame ids (everything outside the largest pointing)", () => {
    // Majority = the 18-frame pointing (ids 1..18); the 12-frame pointing
    // (ids 100..111) are the odd-target frames to reject.
    const frames = [...cluster(18, 10, 20, 1), ...cluster(12, 83, -5, 100)];
    const res = detectMixedPointings(frames);
    expect(res).not.toBeNull();
    expect(res!.minorityIds.length).toBe(12);
    expect([...res!.minorityIds].sort((a, b) => a - b)).toEqual(
      Array.from({ length: 12 }, (_, i) => 100 + i),
    );
    // None of the kept (majority) frames leak into the reject set.
    for (const id of res!.minorityIds) expect(id).toBeGreaterThanOrEqual(100);
  });

  it("includes a lone stray outside the majority in minorityIds too", () => {
    // A bimodal split (20 + 8) plus 3 mis-solved strays far from both: the
    // warning fires on the two substantial pointings, and the odd-frame set is
    // everything but the largest — the 8-frame pointing AND the 3 strays.
    const frames = [
      ...cluster(20, 10, 20, 1),
      ...cluster(8, 83, -5, 100),
      ...cluster(3, 250, 70, 200),
    ];
    const res = detectMixedPointings(frames);
    expect(res).not.toBeNull();
    expect(res!.majority).toBe(20);
    expect(res!.minorityIds.length).toBe(11); // 8 + 3 strays
    for (const id of res!.minorityIds) expect(id).toBeGreaterThanOrEqual(100);
  });

  it("reports three substantial pointings and the two-largest separation", () => {
    const frames = [
      ...cluster(20, 10, 20, 1),
      ...cluster(14, 83, -5, 100),
      ...cluster(8, 200, 40, 200),
    ];
    const res = detectMixedPointings(frames);
    expect(res).not.toBeNull();
    expect(res!.pointings).toBe(3);
    expect(res!.majority).toBe(20);
    expect(res!.others).toBe(22); // 14 + 8
  });

  it("ignores a lone mis-solved stray (second group below the floor)", () => {
    // 20 real subs + 2 frames that solved far away → the stray group is < 5.
    const frames = [...cluster(20, 10, 20, 1), ...cluster(2, 200, 60, 100)];
    expect(detectMixedPointings(frames)).toBeNull();
  });

  it("is null when too few frames to judge", () => {
    expect(detectMixedPointings(cluster(6, 10, 20, 1))).toBeNull();
  });

  it("does not split one pointing straddling RA=0 (wrap-safe)", () => {
    // Frames near RA 359.7 and RA 0.3 are the *same* patch of sky.
    const frames = [...cluster(10, 359.7, 15, 1, 0.2), ...cluster(10, 0.3, 15, 100, 0.2)];
    expect(detectMixedPointings(frames)).toBeNull();
  });

  it("flags two targets that straddle the RA=0 seam", () => {
    // One group near RA 358, another near RA 40 — genuinely different targets,
    // and the wrap-safe distance must still see them as far apart.
    const frames = [...cluster(15, 358, 10, 1), ...cluster(11, 40, 10, 100)];
    const res = detectMixedPointings(frames);
    expect(res).not.toBeNull();
    expect(res!.pointings).toBe(2);
  });

  it("ignores unsolved, unaccepted and coordinate-less frames", () => {
    const frames = [
      ...cluster(18, 10, 20, 1),
      ...cluster(12, 83, -5, 100, 0.3, { accept: false }), // rejected: not counted
      ...cluster(12, 83, -5, 200, 0.3, { solved: false, ra_center_deg: null, dec_center_deg: null }),
    ];
    // Only the one accepted+solved pointing remains → no bimodal split.
    expect(detectMixedPointings(frames)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// The grid linkage has to be the *same answer* as testing every pair, not a
// near-enough one, and it has to stay that way at a scale the all-pairs version
// cannot reach. Both halves are below.
// ---------------------------------------------------------------------------

// The linkage exactly as it was before the spatial grid: every pair, no grid.
// It is the oracle for the equivalence test, and it is deliberately a *copy*
// rather than an export — an oracle that shares code with the thing it checks
// checks nothing.
function exhaustivePartition(frames: Frame[]): number[] | null {
  const pts = frames.filter(
    (f) =>
      f.accept && f.solved &&
      f.ra_center_deg !== null && f.ra_center_deg !== undefined &&
      f.dec_center_deg !== null && f.dec_center_deg !== undefined &&
      Number.isFinite(f.ra_center_deg) && Number.isFinite(f.dec_center_deg),
  );
  if (pts.length < 10) return null;
  const vecs = pts.map((f) => {
    const ra = ((f.ra_center_deg as number) * Math.PI) / 180;
    const dec = ((f.dec_center_deg as number) * Math.PI) / 180;
    const cd = Math.cos(dec);
    return [cd * Math.cos(ra), cd * Math.sin(ra), Math.sin(dec)];
  });
  const cosThresh = Math.cos((3.0 * Math.PI) / 180);
  const parent = pts.map((_, i) => i);
  const find = (i: number): number => {
    let r = i;
    while (parent[r] !== r) r = parent[r];
    while (parent[i] !== r) { const n = parent[i]; parent[i] = r; i = n; }
    return r;
  };
  for (let i = 0; i < vecs.length; i++) {
    for (let j = i + 1; j < vecs.length; j++) {
      const vi = vecs[i], vj = vecs[j];
      if (vi[0] * vj[0] + vi[1] * vj[1] + vi[2] * vj[2] >= cosThresh) {
        parent[find(j)] = find(i);
      }
    }
  }
  return vecs.map((_, i) => find(i));
}

// What the oracle can say about the public result: which frame ids the all-pairs
// linkage puts outside the largest component, and how many components clear the
// substantial floor. Anything else the function returns (counts, centroids, the
// separation) is a pure function of that same partition.
function exhaustiveVerdict(frames: Frame[]) {
  const roots = exhaustivePartition(frames);
  if (roots === null) return null;
  const solved = frames.filter(
    (f) => f.accept && f.solved && Number.isFinite(f.ra_center_deg ?? NaN)
      && Number.isFinite(f.dec_center_deg ?? NaN),
  );
  const counts = new Map<number, number>();
  for (const r of roots) counts.set(r, (counts.get(r) ?? 0) + 1);
  const ordered = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const substantial = ordered.filter(([, c]) => c >= 5);
  if (substantial.length < 2) return null;
  const majorityRoot = substantial[0][0];
  return {
    pointings: substantial.length,
    majority: substantial[0][1],
    others: substantial.slice(1).reduce((s, [, c]) => s + c, 0),
    minorityIds: solved.filter((_, i) => roots[i] !== majorityRoot).map((f) => f.id),
  };
}

// A tiny deterministic PRNG so a failing scene is reproducible from its seed.
function rng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

describe("detectMixedPointings — the grid linkage is the all-pairs linkage", () => {
  it("agrees with an exhaustive all-pairs oracle over 250 random skies", () => {
    const rand = rng(20260917);
    for (let trial = 0; trial < 250; trial++) {
      const frames: Frame[] = [];
      let id = 1;
      const blobs = 1 + Math.floor(rand() * 4);
      for (let b = 0; b < blobs; b++) {
        const ra = rand() * 360;
        // Includes the poles and the RA=0 seam, where the grid could plausibly
        // differ from a great-circle distance if it were an approximation.
        const dec = (rand() * 2 - 1) * 89;
        // Spreads straddling the 3° link distance, where the partition is most
        // sensitive to the exact rule.
        const spread = [0.02, 0.5, 2.0, 2.9, 3.1, 6, 25][Math.floor(rand() * 7)];
        const k = 5 + Math.floor(rand() * 25);
        for (let i = 0; i < k; i++) {
          const d = Math.max(-90, Math.min(90, dec + (rand() - 0.5) * spread));
          const cosd = Math.max(1e-6, Math.cos((d * Math.PI) / 180));
          frames.push(mkFrame(id++, {
            ra_center_deg: ra + ((rand() - 0.5) * spread) / cosd,
            dec_center_deg: d,
          }));
        }
      }
      const got = detectMixedPointings(frames);
      const want = exhaustiveVerdict(frames);
      if (want === null) {
        expect(got, `trial ${trial}`).toBeNull();
      } else {
        expect(got, `trial ${trial}`).not.toBeNull();
        expect(got!.pointings, `trial ${trial}`).toBe(want.pointings);
        expect(got!.majority, `trial ${trial}`).toBe(want.majority);
        expect(got!.others, `trial ${trial}`).toBe(want.others);
        expect(got!.minorityIds, `trial ${trial}`).toEqual(want.minorityIds);
      }
    }
  });

  // The owner's two deepest targets are 5,477 and 35,894 subs, and this runs
  // synchronously inside the Target page's and the Stack form's render, so the
  // cost is a tab that stops responding rather than a slow number. The budget
  // is asserted rather than left to a test timeout: the all-pairs version takes
  // 5–15 s on these scenes and the grid takes single-digit milliseconds, so a
  // loaded CI box has ~40× of headroom on the passing side and the reverted
  // implementation still misses by 3–8×.
  const BUDGET_MS = 1500;

  function millisFor(frames: Frame[]): [number, ReturnType<typeof detectMixedPointings>] {
    const t0 = performance.now();
    const res = detectMixedPointings(frames);
    return [performance.now() - t0, res];
  }

  it("answers a 30,000-sub single pointing inside a frame budget", () => {
    const rand = rng(7);
    const frames = Array.from({ length: 30000 }, (_, i) =>
      mkFrame(i + 1, {
        // Dither is arc-minutes: every sub lands on one pointing, which is the
        // case that cost 15.3 s — all n² pairs are within the link distance.
        ra_center_deg: 83.82 + (rand() - 0.5) * 0.05,
        dec_center_deg: -5.39 + (rand() - 0.5) * 0.05,
      }),
    );
    const [ms, res] = millisFor(frames);
    expect(res).toBeNull();
    expect(ms, `one pointing, 30,000 subs took ${ms.toFixed(0)} ms`).toBeLessThan(BUDGET_MS);
  }, 60000);

  it("still splits two targets at 30,000 subs, inside the same budget", () => {
    const rand = rng(11);
    const frames = Array.from({ length: 30000 }, (_, i) =>
      mkFrame(i + 1, {
        ra_center_deg: (i % 2 === 0 ? 83.82 : 202.5) + (rand() - 0.5) * 0.05,
        dec_center_deg: (i % 2 === 0 ? -5.39 : 47.2) + (rand() - 0.5) * 0.05,
      }),
    );
    const [ms, res] = millisFor(frames);
    expect(res).not.toBeNull();
    expect(res!.pointings).toBe(2);
    expect(res!.majority + res!.others).toBe(30000);
    expect(res!.minorityIds).toHaveLength(15000);
    expect(ms, `two targets, 30,000 subs took ${ms.toFixed(0)} ms`).toBeLessThan(BUDGET_MS);
  }, 60000);

  // A deep mosaic is the case the grid works hardest on: many occupied cubes,
  // each having to link to its neighbours. 24 panels at 1,250 subs each is the
  // owner's shooting shape at his depth.
  it("keeps a 24-panel mosaic one pointing at 30,000 subs, inside the same budget", () => {
    const rand = rng(13);
    const frames = Array.from({ length: 30000 }, (_, i) => {
      const panel = i % 24;
      return mkFrame(i + 1, {
        ra_center_deg: 83.82 + (panel % 6) * 1.0 + (rand() - 0.5) * 0.05,
        dec_center_deg: -5.39 + Math.floor(panel / 6) * 1.0 + (rand() - 0.5) * 0.05,
      });
    });
    const [ms, res] = millisFor(frames);
    expect(res).toBeNull();
    expect(ms, `24-panel mosaic, 30,000 subs took ${ms.toFixed(0)} ms`).toBeLessThan(BUDGET_MS);
  }, 60000);
});
