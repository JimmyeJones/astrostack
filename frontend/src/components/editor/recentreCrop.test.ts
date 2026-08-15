import { describe, expect, it } from "vitest";

import {
  keptFractionWords, recentreCropRect, recentreKeptLabel, recentreRefusalLine,
} from "./recentreCrop";

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

describe("keptFractionWords", () => {
  it("names a simple fraction a beginner reads without arithmetic", () => {
    expect(keptFractionWords(0.21)).toBe("a fifth");
    expect(keptFractionWords(0.33)).toBe("a third");
    expect(keptFractionWords(0.26)).toBe("a quarter");
    expect(keptFractionWords(0.39)).toBe("two fifths");
    expect(keptFractionWords(0.5)).toBe("half");
  });

  it("falls back to a percentage below the smallest simple fraction", () => {
    // "a twentieth" is worse than "5%".
    expect(keptFractionWords(0.05)).toBe("5%");
    expect(keptFractionWords(0.004)).toBe("1%");
  });
});

describe("recentreRefusalLine", () => {
  it("explains the one refusal worth explaining, with the number", () => {
    expect(recentreRefusalLine({ reason: "too_destructive", kept: 0.19 }, "M 31"))
      .toBe("Cropping M 31 back to the middle would leave only about a fifth of "
        + "the picture, so it's better to re-point next session than to crop this one.");
  });

  it("stays silent on every other refusal", () => {
    // Already centred needs no words; "bigger than the frame" is already said by
    // the verdict itself; an unmeasurable picture has nothing honest to add.
    for (const reason of ["centred", "cramped", "unknown_size", "degenerate"]) {
      expect(recentreRefusalLine({ reason, kept: 0.2 }, "M 31")).toBeNull();
    }
    expect(recentreRefusalLine(null, "M 31")).toBeNull();
    expect(recentreRefusalLine(undefined, "M 31")).toBeNull();
  });

  it("stays silent when the kept fraction is missing or nonsense", () => {
    // An older backend, or a value that can't be turned into an honest sentence.
    expect(recentreRefusalLine({ reason: "too_destructive" }, "M 31")).toBeNull();
    expect(recentreRefusalLine(
      { reason: "too_destructive", kept: null }, "M 31")).toBeNull();
    expect(recentreRefusalLine(
      { reason: "too_destructive", kept: 0 }, "M 31")).toBeNull();
    expect(recentreRefusalLine(
      { reason: "too_destructive", kept: 1 }, "M 31")).toBeNull();
    expect(recentreRefusalLine(
      { reason: "too_destructive", kept: Number.NaN }, "M 31")).toBeNull();
  });
});
