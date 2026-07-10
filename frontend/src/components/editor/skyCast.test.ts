import { describe, expect, it } from "vitest";

import { skyCastCaption } from "./skyCast";

describe("skyCastCaption", () => {
  it("returns null with no data or an unknown/empty measurement", () => {
    expect(skyCastCaption(undefined)).toBeNull();
    expect(skyCastCaption(null)).toBeNull();
    expect(skyCastCaption({})).toBeNull();
    expect(
      skyCastCaption({ sky_cast: { r: null, g: null, b: null, neutral: true, cast: "unknown", deviation: 0 } }),
    ).toBeNull();
  });

  it("reads neutral with a reassuring ✓", () => {
    const cap = skyCastCaption({
      sky_cast: { r: 0.2, g: 0.2, b: 0.2, neutral: true, cast: "neutral", deviation: 0.001 },
    });
    expect(cap).not.toBeNull();
    expect(cap!.neutral).toBe(true);
    expect(cap!.text).toContain("neutral");
    expect(cap!.text).toContain("✓");
  });

  it("names a slight cast and its colour", () => {
    const cap = skyCastCaption({
      sky_cast: { r: 0.2, g: 0.24, b: 0.2, neutral: false, cast: "green", deviation: 0.013 },
    });
    expect(cap!.neutral).toBe(false);
    expect(cap!.text).toBe("Sky background has a slight green cast");
  });

  it("drops 'slight' for a strong cast", () => {
    const cap = skyCastCaption({
      sky_cast: { r: 0.2, g: 0.2, b: 0.26, neutral: false, cast: "blue", deviation: 0.05 },
    });
    expect(cap!.text).toBe("Sky background has a blue cast");
  });
});
