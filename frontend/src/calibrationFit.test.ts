import { describe, expect, it } from "vitest";
import {
  biasCanScaleDark, biasSizeWarning, darkScalingBlockedNote, exposureMismatch,
  masterFitsFrames, masterOptionSuffix, masterSizeWarning, tempMismatch,
} from "./calibrationFit";

const SUBS = { width_px: 1080, height_px: 1920 };

describe("masterFitsFrames", () => {
  it("accepts a master built at the target's frame size", () => {
    expect(masterFitsFrames({ width_px: 1080, height_px: 1920 }, SUBS)).toBe(true);
  });

  it("rejects a master from a different camera or binning mode", () => {
    expect(masterFitsFrames({ width_px: 540, height_px: 960 }, SUBS)).toBe(false);
    expect(masterFitsFrames({ width_px: 1080, height_px: 1080 }, SUBS)).toBe(false);
  });

  it("never flags what it cannot disprove", () => {
    // An older master that recorded no size, a target whose frames recorded no
    // size, a backend that doesn't send the frame dims at all, or no pick yet.
    expect(masterFitsFrames({ width_px: null, height_px: null }, SUBS)).toBe(true);
    expect(masterFitsFrames({ width_px: 540, height_px: 960 },
                            { width_px: null, height_px: null })).toBe(true);
    expect(masterFitsFrames({ width_px: 540, height_px: 960 }, {})).toBe(true);
    expect(masterFitsFrames(null, SUBS)).toBe(true);
    expect(masterFitsFrames({ width_px: 540, height_px: 960 }, null)).toBe(true);
  });
});

describe("masterSizeWarning", () => {
  it("names both sizes and says the stack would fail", () => {
    const msg = masterSizeWarning("dark", { width_px: 540, height_px: 960 }, SUBS);
    expect(msg).toContain("540×960");
    expect(msg).toContain("1080×1920");
    expect(msg).toContain("dark");
    expect(msg).toMatch(/fail/);
  });

  it("says nothing for a fitting or unknowable master", () => {
    expect(masterSizeWarning("flat", { width_px: 1080, height_px: 1920 }, SUBS))
      .toBeNull();
    expect(masterSizeWarning("bias", { width_px: null, height_px: null }, SUBS))
      .toBeNull();
    expect(masterSizeWarning("dark", null, SUBS)).toBeNull();
  });
});

describe("masterOptionSuffix", () => {
  it("marks a mismatched master in the picker, before it's chosen", () => {
    expect(masterOptionSuffix({ width_px: 540, height_px: 960 }, SUBS))
      .toBe(" — wrong size for this target");
  });

  it("stays empty for a usable master", () => {
    expect(masterOptionSuffix({ width_px: 1080, height_px: 1920 }, SUBS)).toBe("");
    expect(masterOptionSuffix({ width_px: null, height_px: null }, SUBS)).toBe("");
  });
});


describe("exposureMismatch — the same test the engine applies afterwards", () => {
  it("flags the borderline pair the form used to let through", () => {
    // A 30 s dark on 25 s subs: |25/30 − 1| = 0.167 > 0.15, so
    // CalibrationMasters.calibration_warnings reports it on the finished run.
    // The form's old rule (|30−25|/25 = 0.20 > 0.25?) stayed silent — warn after,
    // not before. Both sides now agree.
    expect(exposureMismatch(30, 25)).toBe(true);
    expect(exposureMismatch(10, 12)).toBe(true);
  });

  it("stays quiet on a genuinely matched pair", () => {
    expect(exposureMismatch(30, 30)).toBe(false);
    // Header rounding on a nominally-matched pair is inside the slack.
    expect(exposureMismatch(30, 29.5)).toBe(false);
    expect(exposureMismatch(10, 10.5)).toBe(false);
  });

  it("measures against the master's exposure, like the engine", () => {
    // Symmetric absolute gap, different denominators: 20 vs 24 is 20% of the
    // master either way; 24 vs 20 would be 20% of the *frames*. Only the
    // master-relative reading matches calibration_warnings.
    expect(exposureMismatch(20, 24)).toBe(true);   // |24/20 − 1| = 0.20
    expect(exposureMismatch(24, 20)).toBe(true);   // |20/24 − 1| = 0.167
    expect(exposureMismatch(20, 22.5)).toBe(false); // 0.125, inside
  });

  it("is one-sided: an unknown or non-positive exposure never warns", () => {
    expect(exposureMismatch(null, 30)).toBe(false);
    expect(exposureMismatch(30, null)).toBe(false);
    expect(exposureMismatch(undefined, undefined)).toBe(false);
    // A bias master records 0 s — dividing by it must not manufacture a warning.
    expect(exposureMismatch(0, 30)).toBe(false);
    expect(exposureMismatch(30, 0)).toBe(false);
  });

  it("prefers the tolerance the server served, and falls back when it can't", () => {
    // A looser served tolerance silences the borderline pair...
    expect(exposureMismatch(30, 25, { exposure_frac: 0.5 })).toBe(false);
    // ...a tighter one catches a pair the default allows.
    expect(exposureMismatch(30, 29.5, { exposure_frac: 0.001 })).toBe(true);
    // An older backend (no block), a null, or a nonsense value → the fallback.
    for (const t of [null, undefined, {}, { exposure_frac: null },
                     { exposure_frac: 0 }, { exposure_frac: -1 },
                     { exposure_frac: Number.NaN }]) {
      expect(exposureMismatch(30, 25, t)).toBe(true);
      expect(exposureMismatch(30, 30, t)).toBe(false);
    }
  });
});

describe("tempMismatch", () => {
  it("fires at or beyond the tolerance and not inside it", () => {
    expect(tempMismatch(20, 5)).toBe(true);
    expect(tempMismatch(5, 10)).toBe(true);     // exactly 5 °C — engine uses >=
    expect(tempMismatch(5, 9)).toBe(false);
    expect(tempMismatch(-10, -12)).toBe(false);
  });

  it("never warns on an unknown or unusable temperature", () => {
    expect(tempMismatch(null, 5)).toBe(false);
    expect(tempMismatch(20, null)).toBe(false);
    expect(tempMismatch(Number.NaN, 5)).toBe(false);
    // 0 °C is a real reading, not a missing one.
    expect(tempMismatch(0, 20)).toBe(true);
  });

  it("honours a served tolerance, falling back on a useless one", () => {
    expect(tempMismatch(20, 12, { temp_c: 10 })).toBe(false);
    expect(tempMismatch(20, 18, { temp_c: 1 })).toBe(true);
    expect(tempMismatch(20, 18, { temp_c: null })).toBe(false);
  });
});


// --- the bias slot: the one master whose size clash isn't fatal ------------
//
// A bias is subtracted from the lights only when no dark is chosen (a dark
// already carries the pedestal), and the engine's `validate` only refuses a
// wrong-sized bias on that path. With a dark chosen its size decides one thing
// instead: whether it can hold the pedestal fixed while the dark is rescaled.

describe("biasSizeWarning", () => {
  it("warns like any other master when the bias IS the calibration", () => {
    const warn = biasSizeWarning({ width_px: 540, height_px: 960 }, SUBS, null);
    expect(warn).toContain("540×960");
    expect(warn).toContain("will fail");
  });

  it("stays silent once a dark is chosen, because the claim would be false", () => {
    // The engine never validates — never even applies — a bias here, so the
    // stack does not fail. Saying it will is worse than saying nothing.
    expect(biasSizeWarning(
      { width_px: 540, height_px: 960 }, SUBS, { width_px: 1080, height_px: 1920 },
    )).toBeNull();
  });

  it("says nothing about a bias that fits, either way", () => {
    const fits = { width_px: 1080, height_px: 1920 };
    expect(biasSizeWarning(fits, SUBS, null)).toBeNull();
    expect(biasSizeWarning(fits, SUBS, fits)).toBeNull();
    expect(biasSizeWarning(null, SUBS, null)).toBeNull();
  });
});

describe("biasCanScaleDark / darkScalingBlockedNote", () => {
  const DARK = { width_px: 1080, height_px: 1920 };

  it("accepts a bias built the same way as the dark", () => {
    expect(biasCanScaleDark({ width_px: 1080, height_px: 1920 }, DARK)).toBe(true);
    expect(darkScalingBlockedNote(DARK, { width_px: 1080, height_px: 1920 })).toBeNull();
  });

  it("explains why scaling will do nothing with a wrong-sized bias", () => {
    const bias = { width_px: 540, height_px: 960 };
    expect(biasCanScaleDark(bias, DARK)).toBe(false);
    const note = darkScalingBlockedNote(DARK, bias);
    // Both sizes, so the user can see which one to rebuild...
    expect(note).toContain("540×960");
    expect(note).toContain("1080×1920");
    // ...and what actually happens to their subs.
    expect(note).toContain("unscaled");
  });

  it("never flags what it cannot disprove", () => {
    expect(biasCanScaleDark({ width_px: null, height_px: null }, DARK)).toBe(true);
    expect(darkScalingBlockedNote(DARK, { width_px: null, height_px: null })).toBeNull();
    expect(darkScalingBlockedNote(DARK, null)).toBeNull();
    expect(darkScalingBlockedNote(null, { width_px: 540, height_px: 960 })).toBeNull();
  });
});
