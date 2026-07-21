import { describe, expect, it } from "vitest";
import { oneFrameCaption, subExposureLabel } from "./oneFrameVsStack";

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
