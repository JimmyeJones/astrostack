import { describe, expect, it } from "vitest";
import {
  DRIZZLE_MIN_SAMPLES_PER_PIXEL,
  samplesPerPixel,
  samplesPerPixelPhrase,
  spreadAcrossPanels,
} from "./samplesPerPixel";

describe("samplesPerPixel", () => {
  it("is the frame count on a single field, where the depth is null", () => {
    expect(samplesPerPixel(250, null)).toBe(250);
    expect(spreadAcrossPanels(250, null)).toBe(false);
  });

  it("is the canvas depth on a mosaic — the owner's 3x3 case", () => {
    // 225 subs across nine field-fulls of sky: a pixel has seen about 25, an
    // order of magnitude below the total every caution used to quote.
    expect(samplesPerPixel(225, 25)).toBe(25);
    expect(spreadAcrossPanels(225, 25)).toBe(true);
  });

  it("reads a missing field as 'no correction', so an older backend is unchanged", () => {
    expect(samplesPerPixel(120, undefined)).toBe(120);
    expect(spreadAcrossPanels(120, undefined)).toBe(false);
  });

  it("refuses a depth that would inflate the count, which is the hiding direction", () => {
    expect(samplesPerPixel(40, 400)).toBe(40);
    expect(samplesPerPixel(40, 0)).toBe(40);
    expect(samplesPerPixel(40, -3)).toBe(40);
    expect(samplesPerPixel(40, Number.NaN)).toBe(40);
    expect(samplesPerPixel(40, Number.POSITIVE_INFINITY)).toBe(40);
  });

  it("floors a fractional depth rather than rounding up to a sample nothing has", () => {
    expect(samplesPerPixel(100, 6.9)).toBe(6);
  });
});

describe("samplesPerPixelPhrase", () => {
  it("keeps today's wording, and its plural, on a single field", () => {
    expect(samplesPerPixelPhrase(250, null)).toBe("250 accepted, solved frames");
    expect(samplesPerPixelPhrase(1, null)).toBe("1 accepted, solved frame");
  });

  it("leads with the depth on a mosaic but still names the total", () => {
    // The total has to appear: the Frames table plainly shows 225, and a
    // sentence that only said 25 would read as the app having lost frames.
    const phrase = samplesPerPixelPhrase(225, 25);
    expect(phrase).toContain("about 25 subs on each patch of sky");
    expect(phrase).toContain("225 in total");
  });

  it("says 'sub', singular, on a one-deep mosaic", () => {
    expect(samplesPerPixelPhrase(9, 1)).toContain("about 1 sub on each patch");
  });
});

describe("the depth the caller passes (#901)", () => {
  // The callers feed `pixel_depth ?? panel_depth`, and the two are different
  // measures of different things. `panel_depth` is the *thinnest* pointing
  // cluster — the right answer to "can this rejection bite anywhere?" and, on
  // the owner's mosaics, ~0.10x the real per-pixel depth, because pointings
  // spaced under a frame's footprint are separate clusters while a pixel sees
  // several of them. These pin what that substitution costs at the one bar the
  // form acts on.

  it("stops sending a deep mosaic the 'turn Drizzle off' advice", () => {
    // Six of the owner's drizzle runs, worded from the thinnest cluster:
    const thinnestCluster = 12;
    expect(samplesPerPixel(1500, thinnestCluster))
      .toBeLessThan(DRIZZLE_MIN_SAMPLES_PER_PIXEL);   // "turn Drizzle off"
    // …and from the canvas, which is what the coverage maps actually measure:
    const perPixel = 128.4;
    expect(samplesPerPixel(1500, perPixel))
      .toBeGreaterThanOrEqual(DRIZZLE_MIN_SAMPLES_PER_PIXEL);  // no caution
  });

  it("still fires the caution on a mosaic that really is thin per pixel", () => {
    // The fix is not "always say the total": a widely-spread raster stays under
    // the bar, and the caution it earns is still correct.
    expect(samplesPerPixel(240, 5.2))
      .toBeLessThan(DRIZZLE_MIN_SAMPLES_PER_PIXEL);
  });

  it("words the phrase from whichever number it is given", () => {
    expect(samplesPerPixelPhrase(1500, 12))
      .toContain("about 12 subs on each patch of sky");
    expect(samplesPerPixelPhrase(1500, 128.4))
      .toContain("about 128 subs on each patch of sky");
  });
});
