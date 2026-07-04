import { describe, expect, it } from "vitest";
import { clippingHistGuides, curvesHistGuides, tonalHistGuides } from "./tonalGuides";
import type { Histogram, OpInstance } from "../../api/client";

const curves = (points: number[][]): OpInstance => ({
  uid: "cv1", id: "tone.curves", enabled: true, params: { points },
});

const levels = (black: number, white: number): OpInstance => ({
  uid: "lv1", id: "tone.levels", enabled: true, params: { black, white },
});

/** A histogram whose extreme bins carry the given fraction of the total, so the
 * clip-edge detection (shared with clippingCaption) trips or doesn't. */
const hist = (lowFrac: number, highFrac: number): Histogram => {
  const bins = 10;
  const mid = 1;
  const arr = new Array(bins).fill(mid);
  // Solve for a total where arr[0]/total = lowFrac and arr[-1]/total = highFrac.
  // Easiest: set the extreme bins to a big count relative to the mid bins.
  const total = 100;
  arr[0] = Math.round(lowFrac * total);
  arr[bins - 1] = Math.round(highFrac * total);
  // Fill the interior so the sum is `total`.
  const interiorSum = total - arr[0] - arr[bins - 1];
  const per = Math.max(0, Math.floor(interiorSum / (bins - 2)));
  for (let i = 1; i < bins - 1; i++) arr[i] = per;
  const edges = Array.from({ length: bins }, (_, i) => i / bins);
  return { bins, edges, r: [...arr], g: [...arr], b: [...arr] };
};

describe("curvesHistGuides", () => {
  it("returns [] for a non-Curves selection or none", () => {
    expect(curvesHistGuides(null)).toEqual([]);
    expect(curvesHistGuides(levels(0.1, 0.8))).toEqual([]);
  });

  it("marks interior control points and skips the pinned endpoints", () => {
    const g = curvesHistGuides(curves([[0, 0], [0.25, 0.2], [0.75, 0.82], [1, 1]]));
    expect(g.map((x) => x.value)).toEqual([0.25, 0.75]);
    expect(g.every((x) => x.dashed && x.color === "#cc5de8")).toBe(true);
  });

  it("returns [] for an identity two-point curve (only endpoints)", () => {
    expect(curvesHistGuides(curves([[0, 0], [1, 1]]))).toEqual([]);
  });

  it("ignores non-finite or malformed points", () => {
    const g = curvesHistGuides(curves([[0, 0], [Number.NaN, 0.5], [0.4, 0.3], [1, 1]]));
    expect(g.map((x) => x.value)).toEqual([0.4]);
  });
});

describe("clippingHistGuides", () => {
  it("returns [] when nothing clips", () => {
    expect(clippingHistGuides(hist(0.0, 0.0))).toEqual([]);
    expect(clippingHistGuides(undefined)).toEqual([]);
  });

  it("marks the white edge (value 1) when highlights clip", () => {
    const g = clippingHistGuides(hist(0.0, 0.1)); // >2% highlight pile
    expect(g).toHaveLength(1);
    expect(g[0]).toMatchObject({ value: 1, label: "clip" });
  });

  it("marks the black edge (value 0) only on a large shadow pile", () => {
    // 10% crushed shadows is below the 35% shadow threshold → no guide.
    expect(clippingHistGuides(hist(0.1, 0.0))).toEqual([]);
    // 50% is above it → one guide at value 0.
    const g = clippingHistGuides(hist(0.5, 0.0));
    expect(g).toHaveLength(1);
    expect(g[0]).toMatchObject({ value: 0, label: "clip" });
  });

  it("marks both edges when highlights and shadows both clip", () => {
    const g = clippingHistGuides(hist(0.5, 0.1));
    expect(g.map((x) => x.value).sort()).toEqual([0, 1]);
  });
});

describe("tonalHistGuides", () => {
  it("composes the Levels, Curves and clipping guides", () => {
    // A Levels op selected + highlights clipping → B/W guides plus a clip edge.
    const g = tonalHistGuides(levels(0.1, 0.8), null, hist(0.0, 0.1));
    expect(g.map((x) => x.label)).toEqual(["B", "W", "clip"]);
  });

  it("adds curve-point guides for a selected Curves op", () => {
    const g = tonalHistGuides(curves([[0, 0], [0.3, 0.4], [1, 1]]), null, hist(0, 0));
    expect(g.map((x) => x.value)).toEqual([0.3]);
  });

  it("shows only clip edges when no tonal op is selected", () => {
    const g = tonalHistGuides(null, null, hist(0.0, 0.1));
    expect(g).toHaveLength(1);
    expect(g[0]).toMatchObject({ value: 1, label: "clip" });
  });
});
