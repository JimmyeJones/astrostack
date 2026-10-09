import { describe, it, expect } from "vitest";

import {
  A_TYPICAL_PART,
  canvasFieldFulls,
  fieldsOfSkyLabel,
  perPixel,
  spansMoreThanOneField,
} from "./perPixel";

describe("canvasFieldFulls", () => {
  it("passes a real mosaic scale straight through", () => {
    expect(canvasFieldFulls(4)).toBe(4);
    expect(canvasFieldFulls(2.25)).toBe(2.25);
  });

  it("reads every absent or degenerate figure as 1.0", () => {
    // The safe direction, and the one that keeps an older backend — and every
    // single-field target — bit-for-bit unchanged on every surface that divides
    // by this. Below 1.0 is clamped rather than honoured: it would *inflate*
    // the apparent depth, which is the direction that hides the bug.
    for (const v of [null, undefined, NaN, Infinity, 0, -3, 0.5, 1]) {
      expect(canvasFieldFulls(v as number | null | undefined)).toBe(1);
    }
  });
});

describe("spansMoreThanOneField", () => {
  it("is true only when a total and a per-pixel figure differ", () => {
    expect(spansMoreThanOneField(4)).toBe(true);
    expect(spansMoreThanOneField(1.01)).toBe(true);
    expect(spansMoreThanOneField(1)).toBe(false);
    expect(spansMoreThanOneField(null)).toBe(false);
    expect(spansMoreThanOneField(undefined)).toBe(false);
  });
});

describe("perPixel", () => {
  it("is the identity on a single field", () => {
    expect(perPixel(3600, null)).toBe(3600);
    expect(perPixel(3600, 1)).toBe(3600);
  });

  it("divides a mosaic's total by the sky its canvas covers", () => {
    expect(perPixel(3600, 4)).toBe(900);
    expect(perPixel(540, 9)).toBe(60);
  });
});

describe("fieldsOfSkyLabel", () => {
  it("rounds to a whole field — the precision would be spurious", () => {
    // "about 4.3 fields" reads as a measurement rather than the rough scale it
    // is, and the scale is all these sentences need.
    expect(fieldsOfSkyLabel(4)).toBe("about 4 fields of sky");
    expect(fieldsOfSkyLabel(3.5)).toBe("about 4 fields of sky");
    expect(fieldsOfSkyLabel(8.7)).toBe("about 9 fields of sky");
  });

  it("does not round one pointing's drift up into a second field", () => {
    // The bug (observer #1095, measured on the owner's library): the count was
    // floored at 2, so a canvas spanning 1.2 fields — one pointing with a
    // night's drift — was announced as "about 2 fields of sky" on 46 of his 50
    // single-field pictures. The scale is still named, and it is now true.
    expect(fieldsOfSkyLabel(1.2)).toBe("a little over one field of sky");
    expect(fieldsOfSkyLabel(1.25)).toBe("a little over one field of sky");
    expect(fieldsOfSkyLabel(1.49)).not.toContain("2 fields");
    // …and it still never says "about 1 field of sky", which would explain
    // nothing to a reader asking why a total and a depth differ.
    expect(fieldsOfSkyLabel(1.2)).not.toContain("about 1 field");
  });

  it("counts fields again as soon as there are two of them", () => {
    // From 1.5 up, rounding cannot answer less than 2 — so the phrase above is
    // exactly the sub-two case and nothing wider gets talked down by it.
    expect(fieldsOfSkyLabel(1.5)).toBe("about 2 fields of sky");
    expect(fieldsOfSkyLabel(2.25)).toBe("about 2 fields of sky");
  });
});

describe("A_TYPICAL_PART", () => {
  it("is what every sentence built on this module's figures says", () => {
    // Not a style preference: `perPixel` is a mean over the canvas and the
    // walk-away hold's own number is a frame-weighted median, so on an uneven
    // mosaic — the owner's shooting style — there are pixels on both sides of
    // it. "each part has N" is a promise the figure cannot keep, and it is the
    // half of the sentence that a beginner reads as a guarantee.
    expect(A_TYPICAL_PART).toBe("a typical part");
  });
});
