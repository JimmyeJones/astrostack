import { describe, expect, it } from "vitest";

import type { EditOp, OpInstance } from "../../api/client";
import {
  autoSkyCastCaption, canNeutraliseSkyCast, NEUTRALIZE_BG_OP_ID,
  neutraliseBackgroundOps, skyCastCaption,
} from "./skyCast";

const greenCast = { r: 0.2, g: 0.24, b: 0.2, neutral: false, cast: "green", deviation: 0.02 };
const stretchOp: OpInstance = { uid: "s1", id: "tone.stretch", enabled: true, params: {} };
const specs: Record<string, EditOp> = {
  [NEUTRALIZE_BG_OP_ID]: {
    id: NEUTRALIZE_BG_OP_ID, label: "Neutralize background", group: "tone",
    stage: "nonlinear", proxy_safe: true, is_stretch: false, help: null,
    params: [{ key: "strength", label: "Strength", type: "float", default: 1.0 } as never],
  },
};

describe("skyCastCaption", () => {
  it("returns null with no data or an unknown/empty measurement", () => {
    expect(skyCastCaption(undefined)).toBeNull();
    expect(skyCastCaption(null)).toBeNull();
    expect(skyCastCaption({})).toBeNull();
    expect(
      skyCastCaption({ sky_cast: { r: null, g: null, b: null, neutral: true, cast: "unknown", deviation: 0 } }),
    ).toBeNull();
  });

  it("reads neutral with a reassuring ✓", () => {
    const cap = skyCastCaption({
      sky_cast: { r: 0.2, g: 0.2, b: 0.2, neutral: true, cast: "neutral", deviation: 0.001 },
    });
    expect(cap).not.toBeNull();
    expect(cap!.neutral).toBe(true);
    expect(cap!.text).toContain("neutral");
    expect(cap!.text).toContain("✓");
  });

  it("names a slight cast and its colour", () => {
    const cap = skyCastCaption({
      sky_cast: { r: 0.2, g: 0.24, b: 0.2, neutral: false, cast: "green", deviation: 0.013 },
    });
    expect(cap!.neutral).toBe(false);
    expect(cap!.text).toBe("Sky background has a slight green cast");
  });

  it("drops 'slight' for a strong cast", () => {
    const cap = skyCastCaption({
      sky_cast: { r: 0.2, g: 0.2, b: 0.26, neutral: false, cast: "blue", deviation: 0.05 },
    });
    expect(cap!.text).toBe("Sky background has a blue cast");
  });
});

describe("autoSkyCastCaption", () => {
  it("returns null with no data or an unknown/empty measurement", () => {
    expect(autoSkyCastCaption(undefined)).toBeNull();
    expect(autoSkyCastCaption(null)).toBeNull();
    expect(autoSkyCastCaption({})).toBeNull();
    expect(
      autoSkyCastCaption({ sky_cast: { r: null, g: null, b: null, neutral: true, cast: "unknown", deviation: 0 } }),
    ).toBeNull();
  });

  it("reads neutral as Auto's result with a reassuring ✓", () => {
    const cap = autoSkyCastCaption({
      sky_cast: { r: 0.2, g: 0.2, b: 0.2, neutral: true, cast: "neutral", deviation: 0.001 },
    });
    expect(cap!.neutral).toBe(true);
    expect(cap!.text).toBe("Auto's background came out neutral ✓");
  });

  it("names a slight cast Auto's colour path left", () => {
    const cap = autoSkyCastCaption({
      sky_cast: { r: 0.2, g: 0.24, b: 0.2, neutral: false, cast: "green", deviation: 0.013 },
    });
    expect(cap!.neutral).toBe(false);
    expect(cap!.text).toBe("Auto's background came out with a slight green cast");
  });

  it("drops 'slight' for a strong cast", () => {
    const cap = autoSkyCastCaption({
      sky_cast: { r: 0.2, g: 0.2, b: 0.26, neutral: false, cast: "magenta", deviation: 0.04 },
    });
    expect(cap!.text).toBe("Auto's background came out with a magenta cast");
  });
});

describe("canNeutraliseSkyCast", () => {
  it("is false with no cast / neutral / unknown", () => {
    expect(canNeutraliseSkyCast(undefined, [stretchOp], true)).toBe(false);
    expect(canNeutraliseSkyCast({}, [stretchOp], true)).toBe(false);
    expect(canNeutraliseSkyCast(
      { sky_cast: { r: 0.2, g: 0.2, b: 0.2, neutral: true, cast: "neutral", deviation: 0.001 } },
      [stretchOp], true)).toBe(false);
    expect(canNeutraliseSkyCast(
      { sky_cast: { r: null, g: null, b: null, neutral: true, cast: "unknown", deviation: 0 } },
      [stretchOp], true)).toBe(false);
  });

  it("needs the fix to land in display space (enabled stretch or already-display)", () => {
    // A real cast but no stretch and not already-display → the appended op would
    // run before the fallback stretch and be re-anchored away, so don't offer it.
    expect(canNeutraliseSkyCast({ sky_cast: greenCast }, [], false)).toBe(false);
    // Enabled stretch → offered.
    expect(canNeutraliseSkyCast({ sky_cast: greenCast }, [stretchOp], true)).toBe(true);
    // Already display-space (no stretch) → offered.
    expect(canNeutraliseSkyCast(
      { sky_cast: greenCast, already_display: true }, [], false)).toBe(true);
  });

  it("does not stack a second neutralise when the last enabled op already is one", () => {
    const neutralise: OpInstance = {
      uid: "n1", id: NEUTRALIZE_BG_OP_ID, enabled: true, params: { strength: 1 },
    };
    expect(canNeutraliseSkyCast(
      { sky_cast: greenCast }, [stretchOp, neutralise], true)).toBe(false);
    // A *disabled* trailing neutralise doesn't count — still offer the fix.
    expect(canNeutraliseSkyCast(
      { sky_cast: greenCast }, [stretchOp, { ...neutralise, enabled: false }], true)).toBe(true);
  });
});

describe("neutraliseBackgroundOps", () => {
  it("appends a neutralise op with its schema defaults at the very end", () => {
    const next = neutraliseBackgroundOps([stretchOp], specs, () => "u1");
    expect(next).toHaveLength(2);
    expect(next[0]).toBe(stretchOp);                 // unchanged, and appended last
    expect(next[1]).toMatchObject({
      uid: "u1", id: NEUTRALIZE_BG_OP_ID, enabled: true, params: { strength: 1.0 },
    });
  });

  it("returns the input unchanged when the op schema isn't loaded", () => {
    const ops = [stretchOp];
    expect(neutraliseBackgroundOps(ops, {}, () => "u1")).toBe(ops);
  });
});
