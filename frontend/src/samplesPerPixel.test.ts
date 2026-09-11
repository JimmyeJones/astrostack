import { describe, expect, it } from "vitest";
import {
  samplesPerPixel,
  samplesPerPixelPhrase,
  spreadAcrossPanels,
} from "./samplesPerPixel";

describe("samplesPerPixel", () => {
  it("is the frame count on a single field, where panel_depth is null", () => {
    expect(samplesPerPixel(250, null)).toBe(250);
    expect(spreadAcrossPanels(250, null)).toBe(false);
  });

  it("is the panel depth on a mosaic — the owner's 3x3 case", () => {
    // 225 subs across nine panels: a pixel has seen about 25, an order of
    // magnitude below the total every caution used to quote.
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
