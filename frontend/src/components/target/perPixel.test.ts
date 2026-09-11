import { describe, it, expect } from "vitest";

import {
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
    // The canvas includes its uncovered corners, so "about 4.3 fields" would
    // read as a measurement rather than the rough scale it is.
    expect(fieldsOfSkyLabel(4)).toBe("about 4 fields of sky");
    expect(fieldsOfSkyLabel(3.5)).toBe("about 4 fields of sky");
    expect(fieldsOfSkyLabel(8.7)).toBe("about 9 fields of sky");
  });

  it("never says 'about 1 field', which would explain nothing", () => {
    // Only ever printed when the canvas really does span more than one field,
    // so a scale that rounds down to 1 still reads as at least 2.
    expect(fieldsOfSkyLabel(1.2)).toBe("about 2 fields of sky");
  });
});
