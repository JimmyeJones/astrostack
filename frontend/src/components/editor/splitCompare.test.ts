import { describe, it, expect } from "vitest";
import { splitFraction, splitClipLeft, splitLeftPct, lookCompareOps } from "./splitCompare";

describe("splitFraction", () => {
  it("maps a pointer inside the box to its fractional x", () => {
    // box spans clientX 100..300 (left 100, width 200); a pointer at 200 is
    // dead-centre → 0.5.
    expect(splitFraction(200, 100, 200)).toBeCloseTo(0.5);
    expect(splitFraction(150, 100, 200)).toBeCloseTo(0.25);
    expect(splitFraction(250, 100, 200)).toBeCloseTo(0.75);
  });

  it("clamps a pointer dragged past either edge to [0,1]", () => {
    expect(splitFraction(50, 100, 200)).toBe(0);    // left of the box
    expect(splitFraction(400, 100, 200)).toBe(1);   // right of the box
    expect(splitFraction(100, 100, 200)).toBe(0);   // exactly the left edge
    expect(splitFraction(300, 100, 200)).toBe(1);   // exactly the right edge
  });

  it("falls back to centre for an unmeasured (zero/negative width) box", () => {
    expect(splitFraction(200, 100, 0)).toBe(0.5);
    expect(splitFraction(200, 100, -5)).toBe(0.5);
  });
});

describe("splitClipLeft", () => {
  it("reveals only the left `fraction` of the element", () => {
    // half → hide the right half (inset right = 50%).
    expect(splitClipLeft(0.5)).toBe("inset(0 50% 0 0)");
    // full left → nothing hidden; none → everything hidden.
    expect(splitClipLeft(1)).toBe("inset(0 0% 0 0)");
    expect(splitClipLeft(0)).toBe("inset(0 100% 0 0)");
  });

  it("clamps out-of-range fractions", () => {
    expect(splitClipLeft(1.5)).toBe("inset(0 0% 0 0)");
    expect(splitClipLeft(-0.5)).toBe("inset(0 100% 0 0)");
  });
});

describe("splitLeftPct", () => {
  it("returns the divider offset as a clamped percent string", () => {
    expect(splitLeftPct(0.25)).toBe("25%");
    expect(splitLeftPct(1.5)).toBe("100%");
    expect(splitLeftPct(-1)).toBe("0%");
  });
});

describe("lookCompareOps", () => {
  it("drops the look's own geometry ops and appends the current edit's framing", () => {
    const look = [
      { id: "tone.stretch" }, { id: "geometry.crop" }, { id: "tone.curves" },
    ];
    const currentGeom = [{ id: "geometry.crop" }, { id: "geometry.rotate" }];
    expect(lookCompareOps(look, currentGeom)).toEqual([
      // the look's tonal ops, in order…
      { id: "tone.stretch" }, { id: "tone.curves" },
      // …then the current recipe's framing so both halves share a frame shape.
      { id: "geometry.crop" }, { id: "geometry.rotate" },
    ]);
  });

  it("is the look verbatim when neither side has geometry ops", () => {
    const look = [{ id: "tone.stretch" }, { id: "detail.sharpen" }];
    expect(lookCompareOps(look, [])).toEqual(look);
  });
});
