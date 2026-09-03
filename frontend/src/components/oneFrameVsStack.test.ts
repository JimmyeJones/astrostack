import { describe, expect, it } from "vitest";
import {
  noiseReductionBadge,
  factorLabel,
  noiseVsExpectedNote,
  oneFrameCaption,
  subExposureLabel,
} from "./oneFrameVsStack";
import factorLabelCases from "./factorLabel.cases.json";

describe("factorLabel", () => {
  // The *same* table `tests/test_factor_label_mirror.py` drives
  // `seestack.stackhealth._factor_label` against, so the badge here and the
  // "How's my stack?" note there cannot describe one stack two ways. Change the
  // rule and you have to change the table, which fails both sides at once.
  it.each(factorLabelCases.cases as [number, string][])(
    "spells %p as %p, the same as the health note does",
    (value, want) => {
      expect(factorLabel(value)).toBe(want);
    });
});

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
  // The *judgement* is the server's (`seestack.stackhealth.noise_vs_expected`,
  // where the measured 0.7·√N threshold and its 10-frame floor live and are
  // pinned against the real estimator). These pin the *sentence* written for it,
  // and that a missing/unknown verdict renders nothing rather than guessing.

  it("says a healthy stack is doing what its frame count should", () => {
    // 505 subs → √505 ≈ 22.5×; a measured 21× is right where it should be.
    expect(noiseVsExpectedNote("expected", 21, 505)).toEqual({
      text: "That's about what 505 subs should give (√505 ≈ 22×).",
      concern: false,
    });
  });

  it("keeps one decimal on a small stack's yardstick", () => {
    // √16 = 4 exactly; √12 ≈ 3.5 — the same rounding rule as the badge.
    expect(noiseVsExpectedNote("expected", 3.9, 16)?.text).toBe(
      "That's about what 16 subs should give (√16 ≈ 4×).");
    expect(noiseVsExpectedNote("expected", 3.2, 12)?.text).toBe(
      "That's about what 12 subs should give (√12 ≈ 3.5×).");
  });

  it("nudges gently when the server reads the stack as low", () => {
    // √400 = 20×; 8× is 0.4·√N — the shape correlated noise (soft alignment,
    // a drifting gradient) produces, measured at 0.45 on real synthetic data.
    const note = noiseVsExpectedNote("low", 8, 400);
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
    const note = noiseVsExpectedNote("low", 1.3, 100);
    expect(note?.concern).toBe(true);
    expect(note?.text).toContain("came in nearer 1.3×");
  });

  it("renders nothing without a verdict from the server", () => {
    // No measurement, too few frames for √N to mean anything, or a build that
    // predates the field: all three arrive as a missing/unknown verdict, and
    // this file must not second-guess any of them with a threshold of its own.
    expect(noiseVsExpectedNote(null, 8, 400)).toBeNull();
    expect(noiseVsExpectedNote(undefined, 8, 400)).toBeNull();
    expect(noiseVsExpectedNote("", 8, 400)).toBeNull();
    expect(noiseVsExpectedNote("something_new", 8, 400)).toBeNull();
  });

  it("stays silent when it cannot name the numbers in the sentence", () => {
    expect(noiseVsExpectedNote("expected", null, 100)).toBeNull();
    expect(noiseVsExpectedNote("expected", undefined, 100)).toBeNull();
    expect(noiseVsExpectedNote("low", Number.NaN, 100)).toBeNull();
    expect(noiseVsExpectedNote("low", 0, 100)).toBeNull();
    expect(noiseVsExpectedNote("expected", 5, null)).toBeNull();
    expect(noiseVsExpectedNote("expected", 5, undefined)).toBeNull();
    expect(noiseVsExpectedNote("expected", 5, Number.NaN)).toBeNull();
    expect(noiseVsExpectedNote("expected", 5, 0)).toBeNull();
  });

  // ---- the mosaic yardstick -------------------------------------------------
  // A mosaic's ratio is measured over a central crop that only ever saw its own
  // panel's subs, so the server judges it against the depth *there* and sends
  // that count. Naming the target's total instead would be a sentence about
  // pixels the measurement never touched.

  it("names the panel depth, not the target total, on a mosaic", () => {
    const note = noiseVsExpectedNote("low", 4, 400, 100, "mosaic_centre");
    expect(note?.concern).toBe(true);
    expect(note?.text).toContain(
      "About 100 subs cover the middle of this mosaic");
    expect(note?.text).toContain("about 10× (√100)");
    expect(note?.text).toContain("came in nearer 4×");
    expect(note?.text).toContain("usually means");
    // The whole-target count must not appear anywhere in the sentence.
    expect(note?.text).not.toContain("400");
  });

  it("reassures a healthy mosaic in the same voice", () => {
    expect(noiseVsExpectedNote("expected", 10, 400, 100, "mosaic_centre")).toEqual({
      text:
        "That's about what the 100 subs covering the middle of this mosaic " +
        "should give (√100 ≈ 10×).",
      concern: false,
    });
  });

  it("uses the server's count whenever it sends one", () => {
    // A single field sends its own frame count as the yardstick; the sentence
    // must read off what the verdict was actually made against, never off a
    // second number the card happens to have.
    expect(noiseVsExpectedNote("expected", 10, 100, 100, "stack")?.text).toBe(
      "That's about what 100 subs should give (√100 ≈ 10×).");
  });

  it("falls back to the run's frame count for a backend that sends neither", () => {
    // Upgrade safety in the other direction: a half-upgraded install must show
    // exactly today's single-field sentence, not nothing.
    expect(noiseVsExpectedNote("expected", 21, 505)?.text).toBe(
      "That's about what 505 subs should give (√505 ≈ 22×).");
    expect(noiseVsExpectedNote("expected", 21, 505, null, null)?.text).toBe(
      "That's about what 505 subs should give (√505 ≈ 22×).");
  });
});
