import { describe, expect, it } from "vitest";
import { clippingCaption } from "./clipping";
import type { Histogram } from "../../api/client";

/** Build a 10-bin histogram with the given per-channel top/bottom-bin counts and
 * a fixed bulk in the middle so fractions are easy to reason about. */
function hist(topR: number, botR: number, bulk = 100): Histogram {
  const chan = (top: number, bot: number) => {
    const a = new Array(10).fill(0);
    a[0] = bot; a[9] = top; a[5] = bulk;
    return a;
  };
  return {
    bins: 10, edges: [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    r: chan(topR, botR), g: chan(0, 0), b: chan(0, 0),
  };
}

describe("clippingCaption", () => {
  it("returns null for a healthy histogram", () => {
    expect(clippingCaption(hist(0, 0))).toBeNull();
  });

  it("warns on highlight clipping above the 2% threshold", () => {
    // top bin = 10 of (10 + 100) ≈ 9% → clipping.
    const msg = clippingCaption(hist(10, 0));
    expect(msg).toMatch(/Highlights are clipping/i);
    expect(msg).toMatch(/9%/);
  });

  it("does not warn on a tiny highlight pile below threshold", () => {
    // top bin = 1 of (1 + 100) ≈ 1% → below the 2% threshold.
    expect(clippingCaption(hist(1, 0))).toBeNull();
  });

  it("only warns on shadows for a large crushed-black pile", () => {
    // bottom bin = 40 of (40 + 100) ≈ 29% → below the 35% shadow threshold.
    expect(clippingCaption(hist(0, 40))).toBeNull();
    // bottom bin = 100 of (100 + 100) = 50% → above threshold.
    const msg = clippingCaption(hist(0, 100));
    expect(msg).toMatch(/Shadows are clipping/i);
    expect(msg).toMatch(/50%/);
  });

  it("reports both when highlights and shadows clip", () => {
    const msg = clippingCaption(hist(10, 100));
    expect(msg).toMatch(/Highlights are clipping/i);
    expect(msg).toMatch(/Shadows are clipping/i);
  });

  it("takes the worst channel (any of r/g/b can trip it)", () => {
    const h = hist(0, 0);
    h.g![9] = 10;  // green highlights blow out even though red is clean
    expect(clippingCaption(h)).toMatch(/Highlights are clipping/i);
  });

  it("is null-safe for missing/empty data", () => {
    expect(clippingCaption(undefined)).toBeNull();
    expect(clippingCaption({ bins: 0, edges: [], r: [], g: [], b: [] })).toBeNull();
  });
});
