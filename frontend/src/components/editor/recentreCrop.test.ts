import { describe, expect, it } from "vitest";

import { recentreCropRect, recentreKeptLabel } from "./recentreCrop";

describe("recentreCropRect", () => {
  it("passes a real proposal through as the editor's crop rectangle", () => {
    expect(recentreCropRect({ x0: 0.1, y0: 0, x1: 0.9, y1: 0.8, kept: 0.64 }))
      .toEqual({ x0: 0.1, y0: 0, x1: 0.9, y1: 0.8 });
  });

  it("makes no offer when there is none", () => {
    // No offer from the backend, and an *older* backend with no field at all.
    expect(recentreCropRect(null)).toBeNull();
    expect(recentreCropRect(undefined)).toBeNull();
  });

  it("refuses a degenerate or out-of-range rectangle rather than cropping to it", () => {
    expect(recentreCropRect({ x0: 0.5, y0: 0, x1: 0.5, y1: 1, kept: 0 })).toBeNull();
    expect(recentreCropRect({ x0: 0.9, y0: 0, x1: 0.1, y1: 1, kept: 0 })).toBeNull();
    expect(recentreCropRect({ x0: -0.1, y0: 0, x1: 1, y1: 1, kept: 1 })).toBeNull();
    expect(recentreCropRect({ x0: 0, y0: 0, x1: 1.5, y1: 1, kept: 1 })).toBeNull();
    expect(recentreCropRect(
      { x0: Number.NaN, y0: 0, x1: 1, y1: 1, kept: 1 })).toBeNull();
  });
});

describe("recentreKeptLabel", () => {
  it("says what fraction of the picture survives the crop", () => {
    expect(recentreKeptLabel({ x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 }))
      .toBe("keeps 64% of the picture");
  });

  it("never claims 100% (the crop always costs something) or 0%", () => {
    expect(recentreKeptLabel({ x0: 0, y0: 0, x1: 1, y1: 1 }))
      .toBe("keeps 99% of the picture");
    expect(recentreKeptLabel({ x0: 0.5, y0: 0.5, x1: 0.501, y1: 0.501 }))
      .toBe("keeps 1% of the picture");
  });
});
