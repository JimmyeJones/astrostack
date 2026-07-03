import { describe, expect, it } from "vitest";
import {
  extraEnabledStretchUids, hasEnabledStretch, insertOnCorrectSide, moveToCorrectSide,
  stageConflicts,
} from "./stageConflicts";
import type { EditOp, OpInstance } from "../../api/client";

function spec(id: string, stage: string, is_stretch = false): EditOp {
  return {
    id, label: id, group: "tone", stage, proxy_safe: true, is_stretch,
    help: null, params: [],
  };
}

const SPECS: Record<string, EditOp> = {
  "background.subtract": spec("background.subtract", "linear"),
  "tone.stretch": spec("tone.stretch", "any", true),
  "tone.saturation": spec("tone.saturation", "nonlinear"),
  "tone.scnr": spec("tone.scnr", "any"),
};

function op(id: string, uid: string, enabled = true): OpInstance {
  return { uid, id, enabled, params: {} };
}

describe("stageConflicts", () => {
  it("flags a linear op sitting after the stretch", () => {
    const ops = [
      op("tone.stretch", "s"),
      op("background.subtract", "bg"),
    ];
    expect(stageConflicts(ops, SPECS)).toEqual({ bg: "linear" });
  });

  it("flags a nonlinear op sitting before the stretch", () => {
    const ops = [
      op("tone.saturation", "sat"),
      op("tone.stretch", "s"),
    ];
    expect(stageConflicts(ops, SPECS)).toEqual({ sat: "nonlinear" });
  });

  it("reports no conflict when everything is on its correct side", () => {
    const ops = [
      op("background.subtract", "bg"),
      op("tone.stretch", "s"),
      op("tone.saturation", "sat"),
    ];
    expect(stageConflicts(ops, SPECS)).toEqual({});
  });

  it("ignores 'any'-stage ops (scnr, the stretch itself) on either side", () => {
    const ops = [
      op("tone.scnr", "a"),
      op("tone.stretch", "s"),
      op("tone.scnr", "b"),
    ];
    expect(stageConflicts(ops, SPECS)).toEqual({});
  });

  it("returns nothing when there is no enabled stretch boundary", () => {
    const ops = [
      op("tone.saturation", "sat"),
      op("background.subtract", "bg"),
      op("tone.stretch", "s", false), // disabled stretch is not a boundary
    ];
    expect(stageConflicts(ops, SPECS)).toEqual({});
  });

  it("ignores disabled ops (they're bypassed anyway)", () => {
    const ops = [
      op("tone.stretch", "s"),
      op("background.subtract", "bg", false),
    ];
    expect(stageConflicts(ops, SPECS)).toEqual({});
  });
});

describe("extraEnabledStretchUids", () => {
  it("returns nothing with a single enabled stretch", () => {
    const ops = [op("background.subtract", "bg"), op("tone.stretch", "s")];
    expect(extraEnabledStretchUids(ops, SPECS)).toEqual([]);
  });

  it("returns every enabled stretch beyond the first, in order", () => {
    const ops = [
      op("tone.stretch", "s1"),
      op("tone.saturation", "sat"),
      op("tone.stretch", "s2"),
      op("tone.stretch", "s3"),
    ];
    expect(extraEnabledStretchUids(ops, SPECS)).toEqual(["s2", "s3"]);
  });

  it("ignores disabled stretches (they don't run)", () => {
    const ops = [
      op("tone.stretch", "s1"),
      op("tone.stretch", "s2", false), // disabled → doesn't compound
    ];
    expect(extraEnabledStretchUids(ops, SPECS)).toEqual([]);
  });

  it("counts only from the first *enabled* stretch", () => {
    const ops = [
      op("tone.stretch", "s0", false), // disabled first
      op("tone.stretch", "s1"),        // first enabled → kept
      op("tone.stretch", "s2"),        // extra
    ];
    expect(extraEnabledStretchUids(ops, SPECS)).toEqual(["s2"]);
  });
});

describe("moveToCorrectSide", () => {
  it("moves a stray linear op to just before the stretch", () => {
    const ops = [
      op("tone.stretch", "s"),
      op("tone.saturation", "sat"),
      op("background.subtract", "bg"),
    ];
    const next = moveToCorrectSide(ops, "bg", SPECS);
    expect(next.map((o) => o.uid)).toEqual(["bg", "s", "sat"]);
  });

  it("moves a stray nonlinear op to just after the stretch", () => {
    const ops = [
      op("tone.saturation", "sat"),
      op("background.subtract", "bg"),
      op("tone.stretch", "s"),
    ];
    const next = moveToCorrectSide(ops, "sat", SPECS);
    expect(next.map((o) => o.uid)).toEqual(["bg", "s", "sat"]);
  });

  it("is a no-op for an 'any'-stage op", () => {
    const ops = [op("tone.stretch", "s"), op("tone.scnr", "a")];
    expect(moveToCorrectSide(ops, "a", SPECS)).toBe(ops);
  });

  it("is a no-op when there is no enabled stretch", () => {
    const ops = [op("background.subtract", "bg"), op("tone.saturation", "sat")];
    expect(moveToCorrectSide(ops, "sat", SPECS)).toBe(ops);
  });
});

describe("insertOnCorrectSide", () => {
  it("inserts a linear op just before the enabled stretch", () => {
    const ops = [op("tone.stretch", "s"), op("tone.saturation", "sat")];
    const next = insertOnCorrectSide(ops, op("background.subtract", "bg"), SPECS);
    expect(next.map((o) => o.uid)).toEqual(["bg", "s", "sat"]);
  });

  it("inserts a nonlinear op just after the enabled stretch", () => {
    const ops = [op("background.subtract", "bg"), op("tone.stretch", "s")];
    const next = insertOnCorrectSide(ops, op("tone.saturation", "sat"), SPECS);
    expect(next.map((o) => o.uid)).toEqual(["bg", "s", "sat"]);
  });

  it("appends an 'any'-stage op at the end (never mis-placed)", () => {
    const ops = [op("tone.stretch", "s")];
    const next = insertOnCorrectSide(ops, op("tone.scnr", "a"), SPECS);
    expect(next.map((o) => o.uid)).toEqual(["s", "a"]);
  });

  it("appends when there is no enabled stretch to anchor against", () => {
    const ops = [op("tone.stretch", "s", false), op("tone.saturation", "sat")];
    const next = insertOnCorrectSide(ops, op("background.subtract", "bg"), SPECS);
    expect(next.map((o) => o.uid)).toEqual(["s", "sat", "bg"]);
  });

  it("appends to an empty pipeline", () => {
    const next = insertOnCorrectSide([], op("background.subtract", "bg"), SPECS);
    expect(next.map((o) => o.uid)).toEqual(["bg"]);
  });
});

describe("hasEnabledStretch", () => {
  it("is true with an enabled stretch op", () => {
    expect(hasEnabledStretch([op("tone.stretch", "s")], SPECS)).toBe(true);
  });

  it("is false with only a disabled stretch op", () => {
    expect(hasEnabledStretch([op("tone.stretch", "s", false)], SPECS)).toBe(false);
  });

  it("is false when no stretch op is present", () => {
    const ops = [op("background.subtract", "bg"), op("tone.saturation", "sat")];
    expect(hasEnabledStretch(ops, SPECS)).toBe(false);
  });
});
