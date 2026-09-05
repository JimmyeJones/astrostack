import { describe, expect, it } from "vitest";
import {
  bayerConflicts, biasCanScaleDark, biasSizeWarning, darkScalingBlockedNote,
  exposureMismatch, flatBayerWarning, flatDarkSizeWarning, flatPickPatch,
  masterFitsFrames, masterOptionSuffix, masterRecommendation, masterSizeWarning,
  pickedMasterContentWarnings,
  tempMismatch,
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

describe("flatDarkSizeWarning", () => {
  const FLAT = { width_px: 1080, height_px: 1920 };

  it("says what actually happens instead of 'stacking will fail'", () => {
    // The engine never validates the flat-dark: it compares it to the flat, and
    // on a mismatch skips the subtraction and stacks anyway. The old shared
    // wording sent the beginner off to fix a stack that was going to succeed,
    // and never mentioned the flat it quietly made worse.
    const warn = flatDarkSizeWarning({ width_px: 540, height_px: 960 }, FLAT);
    expect(warn).toContain("540×960");
    expect(warn).toContain("1080×1920");
    expect(warn).not.toContain("will fail");
    expect(warn).toContain("vignetting");
  });

  it("is measured against the flat, which is the engine's own test", () => {
    // A flat-dark that matches the flat is fine even if neither matches the
    // frames — that clash is the *flat's* blocker, and it is already flagged.
    expect(flatDarkSizeWarning({ width_px: 540, height_px: 960 },
                               { width_px: 540, height_px: 960 })).toBeNull();
  });

  it("never flags what it cannot disprove", () => {
    expect(flatDarkSizeWarning(null, FLAT)).toBeNull();
    expect(flatDarkSizeWarning({ width_px: 540, height_px: 960 }, null)).toBeNull();
    expect(flatDarkSizeWarning({ width_px: null, height_px: null }, FLAT)).toBeNull();
    expect(flatDarkSizeWarning({ width_px: 540, height_px: 960 },
                               { width_px: null, height_px: null })).toBeNull();
  });
});

describe("flatPickPatch", () => {
  it("keeps the flat-dark while there is a flat for it to calibrate", () => {
    expect(flatPickPatch("3")).toEqual({ flat_master_id: "3" });
  });

  it("clears the flat-dark when the flat is cleared", () => {
    // With no flat the engine never loads the flat-dark at all (it lives inside
    // `CalibrationMasters.load`'s `if flat_path:` branch), and the form hides its
    // picker and both its warnings — so a stale pick is submitted, ignored, and
    // invisible.
    expect(flatPickPatch(null)).toEqual({
      flat_master_id: null, flat_dark_master_id: null,
    });
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

// --- masterRecommendation: reconciling "best owned" with "best confident" ----

describe("masterRecommendation", () => {
  const best = {
    dark_master_id: 1, flat_master_id: 3, flat_dark_master_id: 2,
    bias_master_id: 4,
  };

  it("falls back to the best available when the backend sends no confident pick", () => {
    // An older backend, or a library where nothing clears the confidence gates.
    // The form must be exactly as helpful as it was before this existed.
    expect(masterRecommendation(best)).toEqual({
      darkId: 1, flatId: 3, flatDarkId: 2,
      // A dark is recommended, so a bias would be inert (the dark carries it).
      biasId: null, scaleDark: false,
    });
    expect(masterRecommendation({ ...best, confident: {} })).toEqual(
      masterRecommendation(best));
    expect(masterRecommendation(null)).toEqual({
      darkId: null, flatId: null, flatDarkId: null, biasId: null, scaleDark: false,
    });
  });

  it("prefers the master the unattended stack would actually bind", () => {
    // The disagreement this exists for: `recommend_masters` ranks a dark by
    // *combined* distance, so a gain-mismatched but exposure-perfect dark can
    // out-rank the one the walk-away path would use.
    const rec = masterRecommendation({ ...best, confident: { dark_master_id: 9 } });
    expect(rec.darkId).toBe(9);
    // Kinds the confident binding is silent on keep the best-available answer.
    expect(rec.flatId).toBe(3);
  });

  it("keeps a flat-dark with the flat it calibrates", () => {
    // The best-available flat-dark was matched to the best-available *flat*. If
    // the confident binding picked a different flat, that pairing is stale.
    const rec = masterRecommendation({ ...best, confident: { flat_master_id: 7 } });
    expect(rec.flatId).toBe(7);
    expect(rec.flatDarkId).toBeNull();
    const paired = masterRecommendation({
      ...best, confident: { flat_master_id: 7, flat_dark_master_id: 8 },
    });
    expect(paired.flatDarkId).toBe(8);
  });

  it("offers the bias that scales a dark, together with the switch", () => {
    const rec = masterRecommendation({
      ...best,
      confident: { dark_master_id: 1, bias_master_id: 4, scale_dark_to_light: true },
    });
    expect(rec.biasId).toBe(4);
    expect(rec.scaleDark).toBe(true);
  });

  it("never asks to scale a dark it isn't recommending", () => {
    // The switch is only correct as part of the dark+bias pair; half of it would
    // leave the pedestal mis-subtracted.
    const noDark = masterRecommendation({
      ...best, dark_master_id: null,
      confident: { bias_master_id: 4, scale_dark_to_light: true },
    });
    expect(noDark.scaleDark).toBe(false);
    expect(noDark.biasId).toBe(4);
    const noBias = masterRecommendation({
      ...best, confident: { dark_master_id: 1, scale_dark_to_light: true },
    });
    expect(noBias.scaleDark).toBe(false);
  });

  it("recommends a bias for the lights only when no dark is recommended", () => {
    const rec = masterRecommendation({ ...best, dark_master_id: null });
    expect(rec.biasId).toBe(4);
  });
});

const RGGB_SUBS = { width_px: 1080, height_px: 1920, bayer_pattern: "RGGB" };

describe("bayerConflicts", () => {
  it("flags a master built on a different colour-filter phase", () => {
    expect(bayerConflicts({ bayer_pattern: "GRBG" }, RGGB_SUBS)).toBe(true);
  });

  it("treats header case and whitespace as the same sensor", () => {
    expect(bayerConflicts({ bayer_pattern: " rggb " }, RGGB_SUBS)).toBe(false);
  });

  it("never flags what it cannot disprove", () => {
    // A master from before AstroStack stamped BAYERPAT, a target whose frames
    // never recorded one, and anything that isn't a real CFA phase.
    expect(bayerConflicts({}, RGGB_SUBS)).toBe(false);
    expect(bayerConflicts({ bayer_pattern: null }, RGGB_SUBS)).toBe(false);
    expect(bayerConflicts({ bayer_pattern: "GRBG" }, SUBS)).toBe(false);
    expect(bayerConflicts({ bayer_pattern: "MONO" }, RGGB_SUBS)).toBe(false);
    expect(bayerConflicts(null, RGGB_SUBS)).toBe(false);
  });
});

describe("flatBayerWarning", () => {
  it("names both layouts and says the stack will fail", () => {
    const warn = flatBayerWarning({ bayer_pattern: "GRBG" }, RGGB_SUBS);
    expect(warn).toContain("GRBG");
    expect(warn).toContain("RGGB");
    expect(warn).toContain("will fail");
  });

  it("stays silent on a matching flat, an unstamped one, and no pick", () => {
    expect(flatBayerWarning({ bayer_pattern: "RGGB" }, RGGB_SUBS)).toBeNull();
    expect(flatBayerWarning({ bayer_pattern: null }, RGGB_SUBS)).toBeNull();
    expect(flatBayerWarning({ bayer_pattern: "GRBG" }, SUBS)).toBeNull();
    expect(flatBayerWarning(null, RGGB_SUBS)).toBeNull();
  });
});

describe("masterOptionSuffix — colour filter", () => {
  it("badges a flat on another phase, but only a flat", () => {
    const grbg = { width_px: 1080, height_px: 1920, bayer_pattern: "GRBG" };
    expect(masterOptionSuffix(grbg, RGGB_SUBS, "flat"))
      .toBe(" — wrong colour filter for this target");
    // A dark/bias corrects each physical pixel, so its phase changes nothing.
    expect(masterOptionSuffix(grbg, RGGB_SUBS, "dark")).toBe("");
    expect(masterOptionSuffix(grbg, RGGB_SUBS, "bias")).toBe("");
    // And with no kind given (the pre-existing two-argument call) — unchanged.
    expect(masterOptionSuffix(grbg, RGGB_SUBS)).toBe("");
  });

  it("prefers the size clash when a flat is both wrong size and wrong phase", () => {
    expect(masterOptionSuffix(
      { width_px: 540, height_px: 960, bayer_pattern: "GRBG" },
      RGGB_SUBS, "flat",
    )).toBe(" — wrong size for this target");
  });
});

describe("pickedMasterContentWarnings", () => {
  const warn = (message: string) => ({ header_note: { severity: "warn", message } });

  it("names the slot and the master for each disagreeing pick", () => {
    expect(pickedMasterContentWarnings([
      { slot: "dark", master: { name: "Dark 30s", ...warn("40 say they are light frames.") } },
      { slot: "flat", master: { name: "Flat", ...warn("everything else.") } },
    ])).toEqual([
      'Master dark "Dark 30s": 40 say they are light frames.',
      'Master flat "Flat": everything else.',
    ]);
  });

  it("stays silent on a confirmed master, an unnamed kind, and a missing pick", () => {
    // The overwhelmingly common case — the form must not grow a permanent
    // fourth warning block.
    expect(pickedMasterContentWarnings([
      { slot: "dark", master: { name: "D", header_note: { severity: "ok", message: "All 40 say dark." } } },
      { slot: "flat", master: { name: "F", header_note: null } },
      { slot: "bias", master: { name: "B" } },          // built before the check existed
      { slot: "flat-dark", master: null },              // nothing picked
    ])).toEqual([]);
  });

  it("never invents a line out of a warning with no message", () => {
    expect(pickedMasterContentWarnings([
      { slot: "dark", master: { name: "D", header_note: { severity: "warn" } } },
      { slot: "flat", master: { name: "F", header_note: { severity: "warn", message: "" } } },
    ])).toEqual([]);
  });

  it("copes with a master that has no name", () => {
    expect(pickedMasterContentWarnings([{ slot: "bias", master: warn("nope.") }]))
      .toEqual(["Master bias: nope."]);
  });
});
