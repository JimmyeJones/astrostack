import { describe, expect, it } from "vitest";
import {
  NOISE_EXPECTED_LOW_FRACTION,
  NOISE_EXPECTED_MIN_FRAMES,
  noiseReductionBadge,
  noiseVsExpectedNote,
  oneFrameCaption,
  subExposureLabel,
} from "./oneFrameVsStack";

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
  it("says both sides carry the same edit on a recipe-matched run", () => {
    // A "Process target" run shows an *edited* picture, so a beginner looking at
    // it beside a grainy frame has to be told the editing isn't the difference.
    expect(oneFrameCaption(30, 505, "recipe")).toBe(
      "One 30-second frame vs your 505-frame stack — stacking cut the noise " +
      "and pulled out faint detail. Both sides went through the same edit, " +
      "so the only difference is the extra frames.");
  });
  it("stays silent about matching on a plain stack, and on an older backend", () => {
    const plain =
      "One 30-second frame vs your 505-frame stack — stacking cut the noise " +
      "and pulled out faint detail.";
    expect(oneFrameCaption(30, 505, "stretch")).toBe(plain);
    expect(oneFrameCaption(30, 505, null)).toBe(plain);
    expect(oneFrameCaption(30, 505, undefined)).toBe(plain);
  });
});

describe("noiseReductionBadge", () => {
  it("formats a big reduction as a whole number with the sub count", () => {
    expect(noiseReductionBadge(15.3, 228)).toBe(
      "Stacking your 228 subs cut the background noise about 15×.");
  });
  it("formats a small reduction to one decimal", () => {
    expect(noiseReductionBadge(2.36, 4)).toBe(
      "Stacking your 4 subs cut the background noise about 2.4×.");
  });
  it("drops the sub count when it's missing", () => {
    expect(noiseReductionBadge(8, null)).toBe(
      "Stacking your subs cut the background noise about 8×.");
  });
  it("omits the badge for a missing, non-finite, or too-small ratio", () => {
    expect(noiseReductionBadge(null, 100)).toBeNull();
    expect(noiseReductionBadge(undefined, 100)).toBeNull();
    expect(noiseReductionBadge(Number.NaN, 100)).toBeNull();
    expect(noiseReductionBadge(1.2, 100)).toBeNull();   // below the 1.5× floor
  });
  it("rounds 10 to a whole number at the integer/decimal boundary", () => {
    expect(noiseReductionBadge(9.96, 50)).toBe(
      "Stacking your 50 subs cut the background noise about 10×.");
  });
});

describe("noiseVsExpectedNote", () => {
  it("says a healthy stack is doing what its frame count should", () => {
    // 505 subs → √505 ≈ 22.5×; a measured 21× is right where it should be.
    expect(noiseVsExpectedNote(21, 505)).toEqual({
      text: "That's about what 505 subs should give (√505 ≈ 22×).",
      concern: false,
    });
  });

  it("keeps one decimal on a small stack's yardstick", () => {
    // √16 = 4 exactly; √12 ≈ 3.5 — the same rounding rule as the badge.
    expect(noiseVsExpectedNote(3.9, 16)?.text).toBe(
      "That's about what 16 subs should give (√16 ≈ 4×).");
    expect(noiseVsExpectedNote(3.2, 12)?.text).toBe(
      "That's about what 12 subs should give (√12 ≈ 3.5×).");
  });

  it("nudges gently when the stack came in well below √N", () => {
    // √400 = 20×; 8× is 0.4·√N — the shape correlated noise (soft alignment,
    // a drifting gradient) produces, measured at 0.45 on real synthetic data.
    const note = noiseVsExpectedNote(8, 400);
    expect(note?.concern).toBe(true);
    expect(note?.text).toContain("400 subs should cut the noise about 20× (√400)");
    expect(note?.text).toContain("came in nearer 8×");
    // Suggests, never asserts — legitimate rejection and quality weighting both
    // lower the effective frame count.
    expect(note?.text).toContain("usually means");
  });

  it("still speaks when the ratio is below the celebratory badge's floor", () => {
    // The badge hides anything under 1.5×, but a 100-sub stack measuring 1.3×
    // is precisely the run worth saying something about — so this note carries
    // the measured number itself and stands alone.
    expect(noiseReductionBadge(1.3, 100)).toBeNull();
    const note = noiseVsExpectedNote(1.3, 100);
    expect(note?.concern).toBe(true);
    expect(note?.text).toContain("came in nearer 1.3×");
  });

  it("never fires on a healthy or heavily-weighted stack", () => {
    // Measured against the real estimator: an ideal mean stack reads
    // ratio/√N = 0.996–1.012, and weights as spread as U(0.1,1) still read
    // 0.93. Both must read as expected, with margin.
    for (const n of [12, 25, 100, 400]) {
      for (const f of [0.93, 1.0, 1.012, 1.2]) {
        expect(noiseVsExpectedNote(f * Math.sqrt(n), n)?.concern).toBe(false);
      }
    }
  });

  it("stays silent when √N would mean nothing, or nothing was measured", () => {
    expect(noiseVsExpectedNote(2.0, 9)).toBeNull();    // below the 10-frame floor
    expect(noiseVsExpectedNote(2.0, 3)).toBeNull();
    expect(noiseVsExpectedNote(null, 100)).toBeNull();
    expect(noiseVsExpectedNote(undefined, 100)).toBeNull();
    expect(noiseVsExpectedNote(Number.NaN, 100)).toBeNull();
    expect(noiseVsExpectedNote(0, 100)).toBeNull();
    expect(noiseVsExpectedNote(5, null)).toBeNull();
    expect(noiseVsExpectedNote(5, undefined)).toBeNull();
    expect(noiseVsExpectedNote(5, Number.NaN)).toBeNull();
  });

  it("puts the boundary exactly at the measured 0.7·√N", () => {
    const n = 100;
    expect(noiseVsExpectedNote(NOISE_EXPECTED_LOW_FRACTION * Math.sqrt(n), n)?.concern)
      .toBe(false);
    expect(noiseVsExpectedNote(
      NOISE_EXPECTED_LOW_FRACTION * Math.sqrt(n) - 0.01, n)?.concern).toBe(true);
    expect(NOISE_EXPECTED_MIN_FRAMES).toBe(10);
  });
});
