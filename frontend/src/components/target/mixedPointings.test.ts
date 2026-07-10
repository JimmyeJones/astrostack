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
