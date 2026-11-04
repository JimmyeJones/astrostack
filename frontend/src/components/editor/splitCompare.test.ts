import { describe, it, expect } from "vitest";
import { splitFraction, splitClipLeft, splitLeftPct, lookCompareOps, reshapesFrame, nudgeSplit, splitSliderProps } from "./splitCompare";

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

describe("reshapesFrame", () => {
  it("is true for the crop/rotate/resize ops that change the frame shape", () => {
    expect(reshapesFrame("geometry.crop")).toBe(true);
    expect(reshapesFrame("geometry.rotate")).toBe(true);
    expect(reshapesFrame("geometry.resize")).toBe(true);
  });

  it("is false for tone/detail/star ops that leave the frame shape alone", () => {
    expect(reshapesFrame("tone.stretch")).toBe(false);
    expect(reshapesFrame("tone.curves")).toBe(false);
    expect(reshapesFrame("detail.sharpen")).toBe(false);
    expect(reshapesFrame("stars.reduce")).toBe(false);
    expect(reshapesFrame("background.level_coverage")).toBe(false);
  });
});

describe("nudgeSplit", () => {
  it("moves the divider a twentieth per arrow press, a quarter with Shift", () => {
    expect(nudgeSplit(0.5, "ArrowRight", false)).toBe(0.55);
    expect(nudgeSplit(0.5, "ArrowLeft", false)).toBe(0.45);
    expect(nudgeSplit(0.5, "ArrowRight", true)).toBe(0.75);
    expect(nudgeSplit(0.5, "ArrowLeft", true)).toBe(0.25);
    // Up/Down follow the ARIA slider convention (up = larger value).
    expect(nudgeSplit(0.5, "ArrowUp", false)).toBe(0.55);
    expect(nudgeSplit(0.5, "ArrowDown", false)).toBe(0.45);
  });

  it("jumps to either edge on Home/End and stops there", () => {
    expect(nudgeSplit(0.4, "Home", false)).toBe(0);
    expect(nudgeSplit(0.4, "End", false)).toBe(1);
    expect(nudgeSplit(0.98, "ArrowRight", false)).toBe(1);
    expect(nudgeSplit(0.02, "ArrowLeft", true)).toBe(0);
  });

  it("lands on clean twentieths however many presses it takes", () => {
    let f = 0.5;
    for (let i = 0; i < 7; i++) f = nudgeSplit(f, "ArrowLeft", false)!;
    expect(f).toBe(0.15);
  });

  it("leaves every other key to the page (Tab, Ctrl+Z, letters)", () => {
    for (const k of ["Tab", "z", "Enter", " ", "Escape"]) {
      expect(nudgeSplit(0.5, k, false)).toBeNull();
    }
  });

  it("treats a non-finite position as the centre", () => {
    expect(nudgeSplit(Number.NaN, "ArrowRight", false)).toBe(0.55);
  });
});

describe("splitSliderProps", () => {
  it("makes the drag surface a focusable slider that announces its position", () => {
    const p = splitSliderProps(0.25, () => {}, "split divider");
    expect(p.role).toBe("slider");
    expect(p.tabIndex).toBe(0);
    expect(p["aria-label"]).toBe("split divider");
    expect(p["aria-valuenow"]).toBe(25);
    expect(p["aria-valuetext"]).toBe("divider at 25% from the left");
  });
});
