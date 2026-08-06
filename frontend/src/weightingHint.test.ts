import { describe, expect, it } from "vitest";
import { WEIGHTING_MIN_MAX_MIN_FRAMES, minMaxIgnoresWeightingHint } from "./weightingHint";

const base = {
  minMaxReject: true,
  qualityWeighted: true,
  drizzle: false,
  frames: 20 as number | null,
};

describe("minMaxIgnoresWeightingHint", () => {
  it("warns when min/max and quality weighting are both on", () => {
    const hint = minMaxIgnoresWeightingHint(base);
    expect(hint).toMatch(/Min\/max rejection and quality weighting don't combine/);
    expect(hint).toMatch(/order statistic/);
    expect(hint).toMatch(/Use sigma clipping/);
  });

  it("says nothing when either half is off", () => {
    expect(minMaxIgnoresWeightingHint({ ...base, minMaxReject: false })).toBeNull();
    expect(minMaxIgnoresWeightingHint({ ...base, qualityWeighted: false })).toBeNull();
  });

  it("says nothing on the drizzle path, where weights still apply", () => {
    expect(minMaxIgnoresWeightingHint({ ...base, drizzle: true })).toBeNull();
  });

  it("mirrors the engine's frame gate: below 3 frames the weights still apply", () => {
    expect(minMaxIgnoresWeightingHint({ ...base, frames: 2 })).toBeNull();
    expect(minMaxIgnoresWeightingHint({ ...base, frames: WEIGHTING_MIN_MAX_MIN_FRAMES }))
      .toMatch(/don't combine/);
  });

  it("words an unknown frame count conditionally, not as a claim about one run", () => {
    const hint = minMaxIgnoresWeightingHint({ ...base, frames: null });
    expect(hint).toMatch(/On any stack of 3 or more subs/);
    expect(hint).toMatch(/won't affect those stacks/);
    expect(hint).not.toMatch(/this stack/);
  });
});
