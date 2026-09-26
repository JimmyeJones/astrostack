import { describe, expect, it } from "vitest";
import { noiseDeltaSides, noiseDeltaVerdict } from "./noiseDelta";

describe("noiseDeltaSides", () => {
  it("says which half is which, with each side's own date", () => {
    expect(noiseDeltaSides("12 Nov 2026", "18 Nov 2026"))
      .toBe("Left: last time (12 Nov 2026). Right: now (18 Nov 2026).");
  });

  it("drops an empty parenthesis rather than printing a blank one", () => {
    expect(noiseDeltaSides(null, "18 Nov 2026"))
      .toBe("Left: last time. Right: now (18 Nov 2026).");
    expect(noiseDeltaSides(undefined, undefined))
      .toBe("Left: last time. Right: now.");
  });
});

describe("noiseDeltaVerdict", () => {
  it("names the improvement when the newest patch is measurably cleaner", () => {
    expect(noiseDeltaVerdict({ available: true, pixel_exact: true, noise_ratio: 1.42 }))
      .toBe("The grain here is about 1.4× finer than last time.");
  });

  it("drops a trailing .0 rather than saying '2.0×'", () => {
    expect(noiseDeltaVerdict({ available: true, pixel_exact: true, noise_ratio: 2.0 }))
      .toMatch(/about 2× finer/);
  });

  it("says so plainly when the restack came out GRAINIER", () => {
    // A card that can only report good news is decoration, not a measurement.
    const text = noiseDeltaVerdict({
      available: true, pixel_exact: true, noise_ratio: 1 / 1.5,
    });
    expect(text).toMatch(/1\.5× coarser/);
    expect(text).not.toMatch(/finer/);
  });

  it("calls a near-identical patch the same rather than inventing a change", () => {
    expect(noiseDeltaVerdict({ available: true, pixel_exact: true, noise_ratio: 1.05 }))
      .toBe("The grain here is about the same as last time.");
  });

  it("says NOTHING when the two crops were not sampled the same way", () => {
    // A resize lowers the resampled side's per-pixel grain for reasons that have
    // nothing to do with stacking, so the backend withholds the number — and the
    // caption must not manufacture one from a ratio it happens to be handed.
    expect(noiseDeltaVerdict({
      available: true, pixel_exact: false, noise_ratio: 1.9,
    })).toBe("");
  });

  it("says nothing when there is no ratio at all", () => {
    expect(noiseDeltaVerdict({ available: true, noise_ratio: null })).toBe("");
    expect(noiseDeltaVerdict(null)).toBe("");
    expect(noiseDeltaVerdict({ available: true, noise_ratio: 0 })).toBe("");
  });
});
