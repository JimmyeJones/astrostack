import { describe, expect, it } from "vitest";
import {
  WEIGHTING_MIN_MAX_MIN_FRAMES, WEIGHTING_UNUSED_LABEL, minMaxIgnoresWeighting,
  minMaxIgnoresWeightingHint, weightingUnusedNote,
} from "./weightingHint";

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

describe("minMaxIgnoresWeighting (the gate on its own)", () => {
  it("agrees with the sentence it drives, case for case", () => {
    for (const input of [
      base,
      { ...base, minMaxReject: false },
      { ...base, qualityWeighted: false },
      { ...base, drizzle: true },
      { ...base, frames: 2 },
      { ...base, frames: WEIGHTING_MIN_MAX_MIN_FRAMES },
      { ...base, frames: null },
    ]) {
      expect(minMaxIgnoresWeighting(input))
        .toBe(minMaxIgnoresWeightingHint(input) !== null);
    }
  });

  it("answers an unknown frame count conditionally-true, like the wording does", () => {
    expect(minMaxIgnoresWeighting({ ...base, frames: null })).toBe(true);
  });
});

describe("weightingUnusedNote", () => {
  it("speaks about a picture already made, not one about to be", () => {
    const note = weightingUnusedNote(6);
    expect(note).toMatch(/combined 6 subs with min\/max rejection/);
    expect(note).toMatch(/made no difference to this picture/);
    // Past tense throughout: the pre-run caution's "won't affect this stack"
    // reads as something you can still change, and here you cannot.
    expect(note).not.toMatch(/won't affect/);
  });

  it("still explains itself without a frame count", () => {
    expect(weightingUnusedNote(null)).toMatch(/combined these subs with min\/max/);
  });

  it("names the one thing that would change it next time", () => {
    expect(weightingUnusedNote(6)).toMatch(/sigma clipping/);
  });
});

describe("WEIGHTING_UNUSED_LABEL", () => {
  it("is no wider than the chip it stands in for", () => {
    // The Gallery card's badge row wraps, and a longer chip pushes its
    // neighbours down a line on a 280 px card (the v0.438.3 lesson).
    expect(WEIGHTING_UNUSED_LABEL.length).toBeLessThanOrEqual("Quality-weighted".length);
  });
});
