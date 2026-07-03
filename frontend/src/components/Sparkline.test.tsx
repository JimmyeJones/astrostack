import { describe, expect, it } from "vitest";
import { sparklinePoints } from "./Sparkline";

describe("sparklinePoints", () => {
  it("returns no points for an empty series", () => {
    expect(sparklinePoints([], 100, 20)).toEqual([]);
  });

  it("spreads x evenly across the width and inverts y (lower value = lower on screen)", () => {
    const pts = sparklinePoints([0, 1], 100, 20, 2);
    expect(pts).toHaveLength(2);
    // First point at x=0, last at x=width.
    expect(pts[0].x).toBeCloseTo(0);
    expect(pts[1].x).toBeCloseTo(100);
    // Value 0 is the minimum → bottom of the box (largest y, height - pad).
    expect(pts[0].y).toBeCloseTo(18);
    // Value 1 is the maximum → top (smallest y, = pad).
    expect(pts[1].y).toBeCloseTo(2);
  });

  it("centres a flat series vertically and horizontally", () => {
    const pts = sparklinePoints([5], 100, 20);
    expect(pts).toHaveLength(1);
    expect(pts[0].x).toBeCloseTo(50);
    expect(pts[0].y).toBeCloseTo(10);
  });

  it("keeps all points within the vertical padding bounds", () => {
    const pts = sparklinePoints([3, 1, 4, 1, 5, 9, 2], 120, 28, 2);
    for (const p of pts) {
      expect(p.y).toBeGreaterThanOrEqual(2);
      expect(p.y).toBeLessThanOrEqual(26);
    }
  });
});
