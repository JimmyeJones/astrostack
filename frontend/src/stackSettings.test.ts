import { describe, expect, it } from "vitest";
import { MOSAIC_AUTO_OPTIONS, settingOverride } from "./stackSettings";

const mosaic = { options: {}, isMosaic: true, nFramesUsed: 21 };

describe("settingOverride — the canvas overrode the switch", () => {
  it("annotates both passes a mosaic canvas turns on by itself", () => {
    for (const key of MOSAIC_AUTO_OPTIONS) {
      const o = settingOverride(key, { ...mosaic, options: { [key]: false } });
      expect(o?.value).toBe("On — automatic");
      expect(o?.title).toMatch(/a mosaic canvas turns it on itself/);
    }
  });

  it("says nothing on a single field, where the stored Off is the truth", () => {
    for (const key of MOSAIC_AUTO_OPTIONS) {
      expect(settingOverride(key, {
        options: { [key]: false }, isMosaic: false, nFramesUsed: 6,
      })).toBeNull();
    }
  });

  it("says nothing when the canvas is unknown — an older backend, or a run "
    + "recorded before the column existed", () => {
    for (const key of MOSAIC_AUTO_OPTIONS) {
      expect(settingOverride(key, { options: { [key]: false }, nFramesUsed: 21 }))
        .toBeNull();
      expect(settingOverride(key, {
        options: { [key]: false }, isMosaic: null, nFramesUsed: 21,
      })).toBeNull();
    }
  });

  it("leaves a mosaic run that ticked the box alone — 'On' is already right", () => {
    for (const key of MOSAIC_AUTO_OPTIONS) {
      expect(settingOverride(key, { ...mosaic, options: { [key]: true } }))
        .toBeNull();
    }
  });

  it("does not reach any other key on a mosaic", () => {
    for (const key of ["sigma_clip", "background_flatten", "drizzle", "lucky_fraction"]) {
      expect(settingOverride(key, { ...mosaic, options: { [key]: false } }))
        .toBeNull();
    }
  });
});

describe("settingOverride — the combine overrode the switch", () => {
  const ignored = {
    options: { quality_weighted: true, min_max_reject: true },
    isMosaic: false, nFramesUsed: 6,
  };

  it("marks quality weighting the min/max combine threw away", () => {
    const o = settingOverride("quality_weighted", ignored);
    expect(o?.value).toBe("On — not used");
    expect(o?.title).toMatch(/min\/max rejection/);
  });

  it("leaves it alone wherever the weights really applied", () => {
    expect(settingOverride("quality_weighted", {
      ...ignored, options: { quality_weighted: true, sigma_clip: true },
    })).toBeNull();
    // Drizzle honours per-frame weights and runs its own rejection.
    expect(settingOverride("quality_weighted", {
      ...ignored,
      options: { quality_weighted: true, min_max_reject: true, drizzle: true },
    })).toBeNull();
    // Below the engine's own floor min/max falls back to a weighted mean.
    expect(settingOverride("quality_weighted", { ...ignored, nFramesUsed: 2 }))
      .toBeNull();
  });

  it("leaves an untouched switch alone — nothing to annotate when it was off", () => {
    expect(settingOverride("quality_weighted", {
      ...ignored, options: { quality_weighted: false, min_max_reject: true },
    })).toBeNull();
  });

  it("keeps every replacement short enough for the row it sits in", () => {
    // The rows are `wrap="nowrap"` with the label truncating, so a long value
    // eats the setting's own name (the v0.438.3 lesson, one surface over).
    for (const o of [
      settingOverride("quality_weighted", ignored),
      settingOverride(MOSAIC_AUTO_OPTIONS[0], {
        ...mosaic, options: { [MOSAIC_AUTO_OPTIONS[0]]: false },
      }),
    ]) {
      expect(o!.value.length).toBeLessThanOrEqual(16);
    }
  });
});
