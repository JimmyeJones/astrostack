import { describe, expect, it } from "vitest";
import {
  LEVEL_COVERAGE_ID, moveCoverageLevelingToFront, prependCoverageLeveling,
  strandedCoverageLevelingUids,
} from "./coverageLeveling";
import type { EditOp, OpInstance } from "../../api/client";

const LEVEL_SPEC: EditOp = {
  id: LEVEL_COVERAGE_ID, label: "Coverage leveling", group: "background",
  stage: "linear", proxy_safe: true, is_stretch: false, help: null,
  params: [{ key: "object_sigma", label: "Object σ", type: "float", group: "advanced",
             default: 2.0, min: 1, max: 5, step: 0.1, options: null, help: null,
             depends_on: null }],
};
const specs = { [LEVEL_COVERAGE_ID]: LEVEL_SPEC };

const gradient: OpInstance = {
  uid: "g1", id: "background.final_gradient", enabled: true, params: { mode: "luminance" },
};
const mkUid = () => "lc-uid";

describe("prependCoverageLeveling", () => {
  it("prepends a leveling pass with default params on a mosaic", () => {
    const out = prependCoverageLeveling([gradient], true, specs, mkUid);
    expect(out).toHaveLength(2);
    expect(out[0].id).toBe(LEVEL_COVERAGE_ID);
    expect(out[0].params).toEqual({ object_sigma: 2.0 });
    expect(out[0].enabled).toBe(true);
    // Runs before the preset's own ops.
    expect(out[1]).toBe(gradient);
  });

  it("leaves a single-field (non-mosaic) recipe unchanged", () => {
    const ops = [gradient];
    expect(prependCoverageLeveling(ops, false, specs, mkUid)).toBe(ops);
  });

  it("does not duplicate an existing leveling pass", () => {
    const withLevel: OpInstance[] = [
      { uid: "l0", id: LEVEL_COVERAGE_ID, enabled: true, params: { object_sigma: 3 } },
      gradient,
    ];
    expect(prependCoverageLeveling(withLevel, true, specs, mkUid)).toBe(withLevel);
  });

  it("degrades gracefully when the op isn't in the schema", () => {
    const ops = [gradient];
    expect(prependCoverageLeveling(ops, true, {}, mkUid)).toBe(ops);
  });

  it("never mutates the input array", () => {
    const ops = [gradient];
    const out = prependCoverageLeveling(ops, true, specs, mkUid);
    expect(ops).toHaveLength(1);
    expect(out).not.toBe(ops);
  });
});

// The engine skips Coverage leveling outright once an op above it has reshaped
// the frame (pinned in `tests/test_edit_engine.py`: 0.142 of full scale on its
// own, 0.000000 with an aimed Crop/Rotate/Resize above it). These name that op
// so the editor can say so, and move it back where it works.
const level = (uid = "lv"): OpInstance =>
  ({ uid, id: LEVEL_COVERAGE_ID, enabled: true, params: { object_sigma: 2 } });
const geom = (id: string, params: Record<string, unknown>, uid = "g"): OpInstance =>
  ({ uid, id, enabled: true, params });
const AIMED: [string, Record<string, unknown>][] = [
  ["geometry.crop", { x0: 0.12, y0: 0.08, x1: 0.86, y1: 0.93 }],
  ["geometry.rotate", { angle: 7, expand: true }],
  ["geometry.resize", { scale: 0.6 }],
];
const AT_DEFAULTS: [string, Record<string, unknown>][] = [
  ["geometry.crop", { x0: 0, y0: 0, x1: 1, y1: 1 }],
  ["geometry.rotate", { angle: 0, expand: true }],
  ["geometry.resize", { scale: 1 }],
];

describe("strandedCoverageLevelingUids", () => {
  it.each(AIMED)("names a leveling op stranded below an aimed %s", (id, params) => {
    expect(strandedCoverageLevelingUids([geom(id, params), level()])).toEqual(["lv"]);
  });

  // The whole reason the predicate asks `reshapes_frame` rather than "is this a
  // geometry op": all three default to a no-op, so one fresh from the Add menu
  // leaves the frame's shape — and the leveling — alone. Naming it would switch
  // a priority-1 control's own panel to "no effect" while it was working.
  it.each(AT_DEFAULTS)("stays silent for a %s at its own defaults", (id, params) => {
    expect(strandedCoverageLevelingUids([geom(id, params), level()])).toEqual([]);
  });

  it("stays silent when the leveling runs first (Auto's own order)", () => {
    expect(strandedCoverageLevelingUids(
      [level(), geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 })],
    )).toEqual([]);
  });

  it("ignores a disabled geometry op above it, and a disabled leveling op", () => {
    const off = { ...geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 }), enabled: false };
    expect(strandedCoverageLevelingUids([off, level()])).toEqual([]);
    const aimed = geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 });
    expect(strandedCoverageLevelingUids([aimed, { ...level(), enabled: false }])).toEqual([]);
  });

  it("names every stranded instance, and only the stranded ones", () => {
    const aimed = geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 });
    expect(strandedCoverageLevelingUids(
      [level("first"), aimed, level("second"), level("third")],
    )).toEqual(["second", "third"]);
  });

  it("is unmoved by a non-geometry op between the two", () => {
    const aimed = geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 });
    const stretch = { uid: "s", id: "tone.stretch", enabled: true, params: {} };
    expect(strandedCoverageLevelingUids([aimed, stretch, level()])).toEqual(["lv"]);
  });
});

describe("moveCoverageLevelingToFront", () => {
  it("moves the stranded op to the front and clears the stranding", () => {
    const aimed = geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 });
    const ops = [aimed, level()];
    const out = moveCoverageLevelingToFront(ops, strandedCoverageLevelingUids(ops));
    expect(out.map((o) => o.uid)).toEqual(["lv", "g"]);
    expect(strandedCoverageLevelingUids(out)).toEqual([]);
  });

  it("keeps every other op's relative order", () => {
    const aimed = geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 }, "crop");
    const ops: OpInstance[] = [
      { uid: "a", id: "tone.stretch", enabled: true, params: {} },
      aimed,
      level("lv"),
      { uid: "b", id: "tone.curves", enabled: true, params: {} },
    ];
    expect(moveCoverageLevelingToFront(ops, ["lv"]).map((o) => o.uid))
      .toEqual(["lv", "a", "crop", "b"]);
  });

  it("returns the input untouched for an empty or unknown uid list", () => {
    const ops = [level()];
    expect(moveCoverageLevelingToFront(ops, [])).toBe(ops);
    expect(moveCoverageLevelingToFront(ops, ["nope"])).toBe(ops);
  });

  it("never mutates the input array", () => {
    const aimed = geom("geometry.crop", { x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 });
    const ops = [aimed, level()];
    const out = moveCoverageLevelingToFront(ops, ["lv"]);
    expect(ops.map((o) => o.uid)).toEqual(["g", "lv"]);
    expect(out).not.toBe(ops);
  });
});
