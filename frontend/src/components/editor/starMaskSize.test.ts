import { describe, it, expect } from "vitest";
import { starMaskSizePx } from "./starMaskSize";
import type { OpInstance } from "../../api/client";

const op = (id: string, params: Record<string, unknown>): OpInstance =>
  ({ uid: "u1", id, enabled: true, params });

describe("starMaskSizePx", () => {
  it("uses 2× the size for stars.reduce (matches the op's gate)", () => {
    expect(starMaskSizePx(op("stars.reduce", { size: 3 }))).toBe(6);
    expect(starMaskSizePx(op("stars.reduce", { size: 1 }))).toBe(2);
  });

  it("uses the size directly for stars.boost_nebula", () => {
    expect(starMaskSizePx(op("stars.boost_nebula", { size: 5 }))).toBe(5);
  });

  it("falls back to 4 when a star op has no numeric size", () => {
    expect(starMaskSizePx(op("stars.reduce", {}))).toBe(4);
    expect(starMaskSizePx(op("stars.boost_nebula", { size: "x" }))).toBe(4);
  });

  it("returns undefined for a non-star op or no selection (endpoint default)", () => {
    expect(starMaskSizePx(op("tone.saturation", { size: 3 }))).toBeUndefined();
    expect(starMaskSizePx(null)).toBeUndefined();
    expect(starMaskSizePx(undefined)).toBeUndefined();
  });
});
