import { describe, it, expect } from "vitest";
import { curvePointsMatch, isIdentityCurve } from "./curveMatch";
import type { Pt } from "./curveDrag";

const SUGGESTION: Pt[] = [
  [0, 0],
  [0.02, 0.02],
  [0.35, 0.48],
  [0.9, 0.9],
  [1, 1],
];

describe("curvePointsMatch", () => {
  it("matches an identical point list", () => {
    expect(curvePointsMatch(SUGGESTION.map((p) => [...p]), SUGGESTION)).toBe(true);
  });

  it("matches within the tiny epsilon (float round-trip noise)", () => {
    const jittered = SUGGESTION.map(([x, y]) => [x + 2e-4, y - 3e-4]) as Pt[];
    expect(curvePointsMatch(jittered, SUGGESTION)).toBe(true);
  });

  it("does not match when a point is moved beyond epsilon", () => {
    const moved = SUGGESTION.map((p) => [...p]) as Pt[];
    moved[2] = [0.35, 0.6];
    expect(curvePointsMatch(moved, SUGGESTION)).toBe(false);
  });

  it("does not match a different-length list", () => {
    expect(curvePointsMatch([[0, 0], [1, 1]], SUGGESTION)).toBe(false);
  });

  it("does not match an absent/empty suggestion", () => {
    expect(curvePointsMatch(SUGGESTION, null)).toBe(false);
    expect(curvePointsMatch(SUGGESTION, [])).toBe(false);
  });

  it("does not match a missing or malformed current list", () => {
    expect(curvePointsMatch(undefined, SUGGESTION)).toBe(false);
    expect(curvePointsMatch("nope", SUGGESTION)).toBe(false);
    // A point that isn't a numeric pair never matches.
    const bad = SUGGESTION.map((p) => [...p]) as unknown[];
    bad[2] = ["x", "y"];
    expect(curvePointsMatch(bad, SUGGESTION)).toBe(false);
  });
});

describe("isIdentityCurve", () => {
  it("is true only for the untouched [[0,0],[1,1]] default", () => {
    expect(isIdentityCurve([[0, 0], [1, 1]])).toBe(true);
    expect(isIdentityCurve([[0.0, 0.0], [1.0, 1.0]])).toBe(true);
  });

  it("is false once a point is moved or an interior point is added", () => {
    expect(isIdentityCurve([[0, 0], [0.5, 0.6], [1, 1]])).toBe(false);
    expect(isIdentityCurve([[0, 0], [1, 0.9]])).toBe(false);
    expect(isIdentityCurve(SUGGESTION)).toBe(false);
  });

  it("is false for a missing or malformed list", () => {
    expect(isIdentityCurve(undefined)).toBe(false);
    expect(isIdentityCurve([])).toBe(false);
    expect(isIdentityCurve([[0, 0]])).toBe(false);
    expect(isIdentityCurve("nope")).toBe(false);
    expect(isIdentityCurve([["a", "b"], [1, 1]])).toBe(false);
  });
});
