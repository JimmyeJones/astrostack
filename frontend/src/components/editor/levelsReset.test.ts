import { describe, expect, it } from "vitest";
import { LEVELS_IDENTITY, levelsAtIdentity, resetLevelsPoints } from "./levelsReset";

describe("levelsAtIdentity", () => {
  it("is true for neutral / missing params", () => {
    expect(levelsAtIdentity({ black: 0, white: 1, gamma: 1 })).toBe(true);
    expect(levelsAtIdentity({})).toBe(true);
    expect(levelsAtIdentity(undefined)).toBe(true);
  });

  it("is false when any point has been moved", () => {
    expect(levelsAtIdentity({ black: 0.1, white: 1, gamma: 1 })).toBe(false);
    expect(levelsAtIdentity({ black: 0, white: 0.8, gamma: 1 })).toBe(false);
    expect(levelsAtIdentity({ black: 0, white: 1, gamma: 1.6 })).toBe(false);
  });
});

describe("resetLevelsPoints", () => {
  it("restores black/white/gamma to identity while preserving other keys", () => {
    const out = resetLevelsPoints({ black: 0.2, white: 0.7, gamma: 2.0, keep: 42 });
    expect(out).toMatchObject({ ...LEVELS_IDENTITY, keep: 42 });
    expect(levelsAtIdentity(out)).toBe(true);
  });

  it("does not mutate the input", () => {
    const input = { black: 0.3, white: 0.6, gamma: 1.5 };
    resetLevelsPoints(input);
    expect(input).toEqual({ black: 0.3, white: 0.6, gamma: 1.5 });
  });
});
