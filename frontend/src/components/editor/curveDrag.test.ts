import { describe, expect, it } from "vitest";
import {
  addCurvePointInLargestGap, moveCurvePoint, MIN_GAP, nudgeCurvePoint,
  removeCurvePoint, type Pt,
} from "./curveDrag";

describe("moveCurvePoint", () => {
  it("locks the first point's x to 0 and last point's x to 1", () => {
    const pts: Pt[] = [[0, 0], [1, 1]];
    expect(moveCurvePoint(pts, 0, [0.4, 0.3])[0]).toEqual([0, 0.3]);
    expect(moveCurvePoint(pts, 1, [0.6, 0.8])[1]).toEqual([1, 0.8]);
  });

  it("does not let an interior point cross its right neighbour", () => {
    // Drag the middle point (x=0.3) far to the right, past x=0.6.
    const pts: Pt[] = [[0, 0], [0.3, 0.3], [0.6, 0.6], [1, 1]];
    const next = moveCurvePoint(pts, 1, [0.9, 0.9]);
    // It stays index 1 and stops just left of its neighbour — order preserved.
    expect(next[1][0]).toBeLessThan(next[2][0]);
    expect(next[1][0]).toBeCloseTo(0.6 - MIN_GAP, 6);
    expect(next.map((p) => p[0])).toEqual([...next.map((p) => p[0])].sort((a, b) => a - b));
  });

  it("does not let an interior point cross its left neighbour", () => {
    const pts: Pt[] = [[0, 0], [0.3, 0.3], [0.6, 0.6], [1, 1]];
    const next = moveCurvePoint(pts, 2, [0.1, 0.2]);
    expect(next[2][0]).toBeGreaterThan(next[1][0]);
    expect(next[2][0]).toBeCloseTo(0.3 + MIN_GAP, 6);
  });

  it("clamps x and y into [0, 1]", () => {
    const pts: Pt[] = [[0, 0], [0.5, 0.5], [1, 1]];
    const next = moveCurvePoint(pts, 1, [0.5, 1.4]);
    expect(next[1][1]).toBe(1);
    const low = moveCurvePoint(pts, 1, [0.5, -0.3]);
    expect(low[1][1]).toBe(0);
  });

  it("returns a copy and never mutates the input", () => {
    const pts: Pt[] = [[0, 0], [0.5, 0.5], [1, 1]];
    const next = moveCurvePoint(pts, 1, [0.7, 0.2]);
    expect(pts[1]).toEqual([0.5, 0.5]); // original untouched
    expect(next[1]).toEqual([0.7, 0.2]);
  });

  it("sits an interior point between very tight neighbours instead of inverting", () => {
    // Neighbours (index 1 and 3) are closer than 2·MIN_GAP, so index 2 has no
    // valid clamp range and should land at their midpoint rather than invert.
    const pts: Pt[] = [
      [0, 0], [0.5 - MIN_GAP / 4, 0.5], [0.5, 0.5], [0.5 + MIN_GAP / 4, 0.5], [1, 1],
    ];
    const next = moveCurvePoint(pts, 2, [0.9, 0.4]);
    expect(next[2][0]).toBeCloseTo((0.5 - MIN_GAP / 4 + 0.5 + MIN_GAP / 4) / 2, 6);
    expect(next[2][1]).toBe(0.4);
  });
});

describe("nudgeCurvePoint (keyboard access)", () => {
  it("moves an interior point by the given delta, clamped and ordering-safe", () => {
    const pts: Pt[] = [[0, 0], [0.5, 0.5], [1, 1]];
    const next = nudgeCurvePoint(pts, 1, 0.02, -0.03);
    expect(next[1][0]).toBeCloseTo(0.52, 6);
    expect(next[1][1]).toBeCloseTo(0.47, 6);
  });

  it("only moves y for an endpoint (its x stays locked)", () => {
    const pts: Pt[] = [[0, 0], [1, 1]];
    expect(nudgeCurvePoint(pts, 0, -0.1, 0.1)[0]).toEqual([0, 0.1]);
    expect(nudgeCurvePoint(pts, 1, 0.1, -0.1)[1]).toEqual([1, 0.9]);
  });

  it("does not mutate the input", () => {
    const pts: Pt[] = [[0, 0], [0.5, 0.5], [1, 1]];
    nudgeCurvePoint(pts, 1, 0.1, 0.1);
    expect(pts[1]).toEqual([0.5, 0.5]);
  });
});

describe("removeCurvePoint (keyboard access)", () => {
  it("removes an interior point", () => {
    const pts: Pt[] = [[0, 0], [0.5, 0.5], [1, 1]];
    expect(removeCurvePoint(pts, 1)).toEqual([[0, 0], [1, 1]]);
  });

  it("keeps the endpoints (removing one is a no-op copy)", () => {
    const pts: Pt[] = [[0, 0], [0.5, 0.5], [1, 1]];
    expect(removeCurvePoint(pts, 0)).toEqual(pts);
    expect(removeCurvePoint(pts, 2)).toEqual(pts);
  });
});

describe("addCurvePointInLargestGap (keyboard access)", () => {
  it("inserts a point at the midpoint of the widest gap, on the current line", () => {
    // Gaps: 0.3 (0→0.3) and 0.7 (0.3→1). Widest is the second → midpoint x=0.65,
    // y interpolated between 0.4 and 1.0 at (0.65-0.3)/0.7 = 0.5 → 0.7.
    const pts: Pt[] = [[0, 0], [0.3, 0.4], [1, 1]];
    const { points, index } = addCurvePointInLargestGap(pts);
    expect(index).toBe(2);
    expect(points[2][0]).toBeCloseTo(0.65, 6);
    expect(points[2][1]).toBeCloseTo(0.7, 6);
    // Still x-sorted and one longer.
    expect(points.length).toBe(4);
    expect(points.map((p) => p[0])).toEqual([...points.map((p) => p[0])].sort((a, b) => a - b));
  });

  it("adds a mid point to the default identity curve", () => {
    const { points, index } = addCurvePointInLargestGap([[0, 0], [1, 1]]);
    expect(points.length).toBe(3);
    expect(index).toBe(1);
    expect(points[1][0]).toBeCloseTo(0.5, 6);
    expect(points[1][1]).toBeCloseTo(0.5, 6);
  });
});
