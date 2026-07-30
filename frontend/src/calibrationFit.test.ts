import { describe, expect, it } from "vitest";
import {
  masterFitsFrames, masterOptionSuffix, masterSizeWarning,
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
