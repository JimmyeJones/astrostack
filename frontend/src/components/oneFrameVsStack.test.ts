import { describe, expect, it } from "vitest";
import {
  noiseReductionBadge,
  oneFrameCaption,
  subExposureLabel,
} from "./oneFrameVsStack";

describe("subExposureLabel", () => {
  it("labels whole and fractional exposures", () => {
    expect(subExposureLabel(30)).toBe("30-second");
    expect(subExposureLabel(2.5)).toBe("2.5-second");
    expect(subExposureLabel(10.04)).toBe("10-second"); // rounds to one decimal
  });
  it("returns null for a missing or non-positive value", () => {
    expect(subExposureLabel(null)).toBeNull();
    expect(subExposureLabel(undefined)).toBeNull();
    expect(subExposureLabel(0)).toBeNull();
    expect(subExposureLabel(Number.NaN)).toBeNull();
  });
});

describe("oneFrameCaption", () => {
  it("uses both the sub exposure and the frame count when present", () => {
    expect(oneFrameCaption(30, 505)).toBe(
      "One 30-second frame vs your 505-frame stack — stacking cut the noise " +
      "and pulled out faint detail.");
  });
  it("drops the exposure clause when it's missing", () => {
    expect(oneFrameCaption(null, 505)).toBe(
      "One frame vs your 505-frame stack — stacking cut the noise " +
      "and pulled out faint detail.");
  });
  it("falls back to a generic line with no provenance", () => {
    expect(oneFrameCaption(null, null)).toBe(
      "One frame vs your stack — stacking cut the noise and pulled out faint detail.");
  });
});

describe("noiseReductionBadge", () => {
  it("formats a big reduction as a whole number with the sub count", () => {
    expect(noiseReductionBadge(15.3, 228)).toBe(
      "Stacking your 228 subs cut the background noise about 15×.");
  });
  it("formats a small reduction to one decimal", () => {
    expect(noiseReductionBadge(2.36, 4)).toBe(
      "Stacking your 4 subs cut the background noise about 2.4×.");
  });
  it("drops the sub count when it's missing", () => {
    expect(noiseReductionBadge(8, null)).toBe(
      "Stacking your subs cut the background noise about 8×.");
  });
  it("omits the badge for a missing, non-finite, or too-small ratio", () => {
    expect(noiseReductionBadge(null, 100)).toBeNull();
    expect(noiseReductionBadge(undefined, 100)).toBeNull();
    expect(noiseReductionBadge(Number.NaN, 100)).toBeNull();
    expect(noiseReductionBadge(1.2, 100)).toBeNull();   // below the 1.5× floor
  });
  it("rounds 10 to a whole number at the integer/decimal boundary", () => {
    expect(noiseReductionBadge(9.96, 50)).toBe(
      "Stacking your 50 subs cut the background noise about 10×.");
  });
});
