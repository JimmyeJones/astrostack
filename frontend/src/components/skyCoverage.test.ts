import { describe, expect, it } from "vitest";
import {
  describeSkyCoverage,
  formatSkyArea,
  formatSkyFraction,
  FULL_MOON_DEG2,
} from "./skyCoverage";

describe("formatSkyFraction", () => {
  it("keeps a real astro library's tiny fraction readable", () => {
    // ~18 deg² of a 41,253 deg² sky. toFixed(1) would render this "0.0%".
    expect(formatSkyFraction(18.4 / 41252.96)).toBe("0.045%");
  });

  it("says so plainly rather than rounding a first light to zero", () => {
    // One Seestar field (~1.3 deg²) still gets a real number…
    expect(formatSkyFraction(1.3 / 41252.96)).toBe("0.003%");
    // …and something genuinely below the last digit says that, not "0.000%".
    expect(formatSkyFraction(0.2 / 41252.96)).toBe("less than 0.001%");
    expect(formatSkyFraction(0)).toBe("0%");
  });

  it("loosens the precision as the number grows", () => {
    expect(formatSkyFraction(0.05)).toBe("5.0%");
    expect(formatSkyFraction(0.5)).toBe("50%");
  });
});

describe("formatSkyArea", () => {
  it("suits its precision to the magnitude", () => {
    expect(formatSkyArea(0.34)).toBe("0.34");
    expect(formatSkyArea(18.43)).toBe("18.4");
    expect(formatSkyArea(1234.6)).toBe("1235");
    expect(formatSkyArea(0)).toBe("0");
  });
});

describe("describeSkyCoverage", () => {
  it("anchors the area in the one patch of sky a beginner can picture", () => {
    const s = describeSkyCoverage(18.4, 18.4 / 41252.96, 12);
    expect(s).toContain("12 pictures");
    expect(s).toContain("18.4 square degrees");
    expect(s).toContain(`${Math.round(18.4 / FULL_MOON_DEG2)} full Moons`);
    expect(s).toContain("0.045% of the whole sky");
  });

  // This test's name was already right and its assertion was not: it pinned
  // "Your 1 picture cover" — the subject and the verb disagreeing — which is
  // what a beginner reads on the Dashboard the day they make their first
  // picture, i.e. the single most-seen state of this sentence.
  it("reads naturally on a first picture", () => {
    const s = describeSkyCoverage(1.3, 1.3 / 41252.96, 1);
    expect(s).toContain("Your picture covers 1.3 square degrees");
    expect(s).not.toContain("picture cover ");
    expect(s).toContain("full Moons");
  });

  it("keeps the count and the plural verb once there is more than one", () => {
    const s = describeSkyCoverage(18.4, 18.4 / 41252.96, 12);
    expect(s).toContain("Your 12 pictures cover 18.4 square degrees");
  });

  it("drops the plural when the whole library is about one moon", () => {
    expect(describeSkyCoverage(0.21, 0.21 / 41252.96, 1))
      .toContain("about a full Moon's worth of sky");
  });

  // Overlapping pictures are counted once server-side, which makes the number
  // *smaller* than adding the pictures up would. That is the honest total, but
  // an owner who watched it drop deserves the reason in the same sentence.
  it("explains itself when overlapping pictures visibly changed the number", () => {
    const s = describeSkyCoverage(12.0, 12.0 / 41252.96, 5, 18.4);
    expect(s).toContain("12.0 square degrees");
    expect(s).toContain("Where two of them overlap, that patch counts once.");
  });

  it("stays quiet about overlap that doesn't move the number it shows", () => {
    // A sliver of shared sky, too small to change the rendered figure — the
    // clause would be an explanation of nothing.
    const s = describeSkyCoverage(18.4, 18.4 / 41252.96, 12, 18.401);
    expect(s).not.toContain("overlap");
    // …as is the ordinary case of no overlap at all, and an older backend
    // that doesn't send the naive total.
    expect(describeSkyCoverage(18.4, 18.4 / 41252.96, 12, 18.4))
      .not.toContain("overlap");
    expect(describeSkyCoverage(18.4, 18.4 / 41252.96, 12)).not.toContain("overlap");
  });

  it("says nothing at all when there is nothing to measure", () => {
    expect(describeSkyCoverage(0, 0, 0)).toBe("");
    expect(describeSkyCoverage(12, 0.0003, 0)).toBe("");
  });
});
