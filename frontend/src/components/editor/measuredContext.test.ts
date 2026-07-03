import { describe, it, expect } from "vitest";
import { coalesceFwhm, measuredContextText } from "./measuredContext";

describe("coalesceFwhm", () => {
  it("returns the first finite positive value", () => {
    expect(coalesceFwhm(null, 3.2, 4.0)).toBe(3.2);
    expect(coalesceFwhm(undefined, null, 4.0)).toBe(4.0);
  });
  it("skips non-finite and non-positive values", () => {
    expect(coalesceFwhm(NaN, 0, -1, 2.5)).toBe(2.5);
  });
  it("returns null when nothing is usable", () => {
    expect(coalesceFwhm(null, undefined, NaN, 0)).toBeNull();
  });
});

describe("measuredContextText", () => {
  it("combines FWHM and noise into one line", () => {
    expect(measuredContextText({ fwhm_px: 3.24, noise_sigma: 0.0213 }))
      .toBe("Measured: stars ≈ 3.2 px FWHM · background noise σ 0.021");
  });
  it("shows just the FWHM when noise is missing", () => {
    expect(measuredContextText({ fwhm_px: 2.5, noise_sigma: null }))
      .toBe("Measured: stars ≈ 2.5 px FWHM");
  });
  it("shows just the noise when FWHM is missing", () => {
    expect(measuredContextText({ fwhm_px: null, noise_sigma: 0.05 }))
      .toBe("Measured: background noise σ 0.050");
  });
  it("returns null when nothing was measured", () => {
    expect(measuredContextText({ fwhm_px: null, noise_sigma: null })).toBeNull();
    expect(measuredContextText({})).toBeNull();
  });
  it("ignores non-positive FWHM and non-finite noise", () => {
    expect(measuredContextText({ fwhm_px: 0, noise_sigma: NaN })).toBeNull();
  });
});
