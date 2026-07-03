import { describe, expect, it } from "vitest";
import type { EditOp, OpInstance } from "../../api/client";
import { applyTrimCrop, trimRectStyle, trimKeptLabel } from "./mosaicTrim";

const specs: Record<string, EditOp> = {
  "tone.stretch": { id: "tone.stretch", label: "Stretch", group: "tone",
    stage: "any", is_stretch: true, params: [] } as unknown as EditOp,
  "geometry.crop": { id: "geometry.crop", label: "Crop", group: "stars_geometry",
    stage: "nonlinear", params: [
      { key: "x0", label: "Left", type: "float", default: 0 },
      { key: "y0", label: "Top", type: "float", default: 0 },
      { key: "x1", label: "Right", type: "float", default: 1 },
      { key: "y1", label: "Bottom", type: "float", default: 1 },
    ] } as unknown as EditOp,
};

const crop = { x0: 0.2, y0: 0.1, x1: 0.8, y1: 0.9 };
const makeUid = () => "fixed123";

describe("applyTrimCrop", () => {
  it("adds a new crop op seeded with defaults and the bounds", () => {
    const out = applyTrimCrop([], crop, specs, makeUid);
    expect(out).toHaveLength(1);
    expect(out[0].id).toBe("geometry.crop");
    expect(out[0].enabled).toBe(true);
    expect(out[0].params).toEqual({ x0: 0.2, y0: 0.1, x1: 0.8, y1: 0.9 });
  });

  it("inserts a new crop after an enabled stretch (nonlinear stage)", () => {
    const ops: OpInstance[] = [
      { uid: "a", id: "tone.stretch", enabled: true, params: {} },
    ];
    const out = applyTrimCrop(ops, crop, specs, makeUid);
    expect(out.map((o) => o.id)).toEqual(["tone.stretch", "geometry.crop"]);
  });

  it("updates and enables an existing crop op instead of adding a duplicate", () => {
    const ops: OpInstance[] = [
      { uid: "c", id: "geometry.crop", enabled: false,
        params: { x0: 0, y0: 0, x1: 1, y1: 1 } },
    ];
    const out = applyTrimCrop(ops, crop, specs, makeUid);
    expect(out).toHaveLength(1);
    expect(out[0].uid).toBe("c");           // same op, not a new one
    expect(out[0].enabled).toBe(true);
    expect(out[0].params).toMatchObject(crop);
  });

  it("does not mutate the input array", () => {
    const ops: OpInstance[] = [
      { uid: "a", id: "tone.stretch", enabled: true, params: {} },
    ];
    const snapshot = JSON.stringify(ops);
    applyTrimCrop(ops, crop, specs, makeUid);
    expect(JSON.stringify(ops)).toBe(snapshot);
  });

  it("appends when the crop spec is not loaded", () => {
    const out = applyTrimCrop([], crop, {}, makeUid);
    expect(out).toHaveLength(1);
    expect(out[0].params).toEqual(crop);
  });
});

describe("trimRectStyle", () => {
  it("maps fractional bounds to image-space percentages", () => {
    expect(trimRectStyle(crop)).toEqual({
      left: "20.00%", top: "10.00%", width: "60.00%", height: "80.00%",
    });
  });

  it("handles a full-frame (no-trim) rectangle", () => {
    expect(trimRectStyle({ x0: 0, y0: 0, x1: 1, y1: 1 })).toEqual({
      left: "0.00%", top: "0.00%", width: "100.00%", height: "100.00%",
    });
  });
});

describe("trimKeptLabel", () => {
  it("summarises the kept fraction in plain language", () => {
    expect(trimKeptLabel(crop)).toBe("keeps the central 60% × 80%");
  });
});
