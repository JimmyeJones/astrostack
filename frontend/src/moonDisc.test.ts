import { describe, it, expect } from "vitest";
import type { ScaleBar } from "./api/client";
import {
  MOON_DIAMETER_ARCSEC,
  MOON_DISC_MAX_SHORT_FRACTION,
  moonDiscFits,
  moonDiscFraction,
  moonDiscLayout,
} from "./moonDisc";

/** A bar on a field four full Moons wide — the owner's S30 shape. */
const bar: ScaleBar = {
  arcsec: 1800,
  label: "30′",
  fraction: 1800 / (4 * MOON_DIAMETER_ARCSEC),
  frame_arcmin: (4 * MOON_DIAMETER_ARCSEC) / 60,
  moon_comparison: "the whole frame is about 4.0 full Moons wide",
};

describe("moonDiscFraction", () => {
  it("is the Moon's true share of the frame width", () => {
    expect(moonDiscFraction(bar)).toBeCloseTo(0.25, 12);
  });

  it("agrees with the sentence it illustrates", () => {
    // A frame the sentence calls "N full Moons wide" must draw a disc 1/N of it,
    // or the picture says one thing and shows another.
    for (const moons of [1.5, 2.5, 4, 9]) {
      const b = { ...bar, fraction: bar.arcsec / (moons * MOON_DIAMETER_ARCSEC) };
      expect(moonDiscFraction(b)).toBeCloseTo(1 / moons, 12);
    }
  });

  it("rides on `fraction`, so a re-based bar carries it", () => {
    // The crop and North-up paths re-base `fraction` and nothing else. Deriving
    // from it is what makes the disc follow them without its own arithmetic.
    expect(moonDiscFraction({ ...bar, fraction: bar.fraction * 0.7 }))
      .toBeCloseTo(0.25 * 0.7, 12);
  });

  it("is honest above 1 on a field tighter than the Moon", () => {
    // A 200″-wide frame with a 30″ bar — about a ninth of a Moon across.
    expect(moonDiscFraction({ ...bar, arcsec: 30, fraction: 30 / 200 }))
      .toBeCloseTo(MOON_DIAMETER_ARCSEC / 200, 9);
  });

  it("is 0 rather than NaN for a bar that cannot answer", () => {
    expect(moonDiscFraction(null)).toBe(0);
    expect(moonDiscFraction(undefined)).toBe(0);
    expect(moonDiscFraction({ ...bar, arcsec: 0 })).toBe(0);
    expect(moonDiscFraction({ ...bar, fraction: 0 })).toBe(0);
    expect(moonDiscFraction({ ...bar, arcsec: NaN })).toBe(0);
    expect(moonDiscFraction({ ...bar, fraction: Infinity })).toBe(0);
  });
});

describe("moonDiscFits", () => {
  it("accepts a field where the Moon is still a mark on the picture", () => {
    expect(moonDiscFits(bar, 1000, 600)).toBe(true);
  });

  it("declines once the Moon would swamp the short side", () => {
    // Square picture: the ceiling bites at exactly MOON_DISC_MAX_SHORT_FRACTION.
    const justUnder = { ...bar, fraction: bar.fraction };
    expect(moonDiscFits(justUnder, 1000, 1000)).toBe(true);
    const over = {
      ...bar,
      fraction: bar.fraction * ((MOON_DISC_MAX_SHORT_FRACTION / 0.25) + 0.1),
    };
    expect(moonDiscFits(over, 1000, 1000)).toBe(false);
  });

  it("judges against the short side, so a tall picture is stricter", () => {
    // 0.25 of the width is 0.625 of a picture only 400 px tall → over the cap.
    expect(moonDiscFits(bar, 1000, 400)).toBe(false);
    expect(moonDiscFits(bar, 1000, 600)).toBe(true);
  });

  it("declines an unmeasured picture or an unusable bar", () => {
    expect(moonDiscFits(bar, 0, 600)).toBe(false);
    expect(moonDiscFits(bar, 1000, 0)).toBe(false);
    expect(moonDiscFits(null, 1000, 600)).toBe(false);
  });
});

describe("moonDiscLayout", () => {
  it("scales the disc to the rendered (contain-fit) width", () => {
    // 1000×600 in a 500×300 box → scale 0.5 → renderW 500 → disc 0.25·500 = 125.
    expect(moonDiscLayout(bar, 1000, 600, 500, 300)).toEqual({ diameterPx: 125 });
  });

  it("uses the letterbox-limited width when the box is a different aspect", () => {
    expect(moonDiscLayout(bar, 1000, 600, 1000, 300)).toEqual({ diameterPx: 125 });
  });

  it("places nothing the `fits` test declines, at any box size", () => {
    // One rule in one place: a control that offers the disc on `moonDiscFits`
    // can never meet a layout that then refuses to place it.
    expect(moonDiscLayout(bar, 1000, 400, 500, 200)).toBeNull();
    expect(moonDiscLayout(bar, 1000, 400, 2000, 800)).toBeNull();
  });

  it("returns null for an unmeasured box or a bar that cannot answer", () => {
    expect(moonDiscLayout(bar, 1000, 600, 0, 300)).toBeNull();
    expect(moonDiscLayout(bar, 1000, 600, 500, 0)).toBeNull();
    expect(moonDiscLayout(null, 1000, 600, 500, 300)).toBeNull();
  });
});
