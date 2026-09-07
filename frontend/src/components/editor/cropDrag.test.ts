import { describe, it, expect } from "vitest";

import {
  MIN_CROP_FRAC, FULL_CROP, applyCropDrag, bigCropNote, cropDragBlockedReason,
  cropFromParams, cropHandlePositions, cropKeptLabel, cropToParams, existingCropUid, isFullFrame,
  pointerFraction, type CropDragStart, type CropHandle,
} from "./cropDrag";
import type { OpInstance } from "../../api/client";

const op = (uid: string, id: string, enabled = true): OpInstance =>
  ({ uid, id, enabled, params: {} } as OpInstance);

const start = (handle: CropHandle, crop = FULL_CROP, fx = 0, fy = 0): CropDragStart =>
  ({ handle, crop, fx, fy });

describe("cropFromParams", () => {
  it("defaults a fresh crop op to the whole frame", () => {
    expect(cropFromParams({})).toEqual(FULL_CROP);
    expect(cropFromParams(undefined)).toEqual(FULL_CROP);
    expect(cropFromParams(null)).toEqual(FULL_CROP);
  });

  it("reads the four fractions through", () => {
    expect(cropFromParams({ x0: 0.1, y0: 0.2, x1: 0.8, y1: 0.9 }))
      .toEqual({ x0: 0.1, y0: 0.2, x1: 0.8, y1: 0.9 });
  });

  it("sorts a reversed pair the way the engine's crop_bounds does", () => {
    expect(cropFromParams({ x0: 0.8, x1: 0.2, y0: 0.9, y1: 0.3 }))
      .toEqual({ x0: 0.2, x1: 0.8, y0: 0.3, y1: 0.9 });
  });

  it("clamps out-of-range and non-finite values instead of throwing", () => {
    expect(cropFromParams({ x0: -3, x1: 7, y0: NaN, y1: "oops" }))
      .toEqual(FULL_CROP);
  });
});

describe("cropToParams", () => {
  it("rounds to the sliders' own step so a drag and a typed value match", () => {
    expect(cropToParams({ x0: 0.1234567, y0: 0.2, x1: 0.87654321, y1: 0.9 }))
      .toEqual({ x0: 0.123, y0: 0.2, x1: 0.877, y1: 0.9 });
  });

  it("round-trips through cropFromParams", () => {
    const c = { x0: 0.25, y0: 0.125, x1: 0.75, y1: 0.875 };
    expect(cropFromParams(cropToParams(c))).toEqual(c);
  });
});

describe("pointerFraction", () => {
  const box = { left: 100, top: 50, width: 400, height: 200 };

  it("maps a client point to a fraction of the box", () => {
    expect(pointerFraction(300, 150, box)).toEqual({ fx: 0.5, fy: 0.5 });
    expect(pointerFraction(100, 50, box)).toEqual({ fx: 0, fy: 0 });
    expect(pointerFraction(500, 250, box)).toEqual({ fx: 1, fy: 1 });
  });

  it("pins a drag that leaves the box to the edge", () => {
    expect(pointerFraction(-500, 9999, box)).toEqual({ fx: 0, fy: 1 });
  });

  it("degrades to the origin on a zero-sized box rather than dividing by zero", () => {
    expect(pointerFraction(10, 10, { left: 0, top: 0, width: 0, height: 0 }))
      .toEqual({ fx: 0, fy: 0 });
  });
});

describe("applyCropDrag — edges and corners", () => {
  it("moves only the edge that was grabbed", () => {
    expect(applyCropDrag(start("w"), 0.3, 0.9))
      .toEqual({ x0: 0.3, y0: 0, x1: 1, y1: 1 });
    expect(applyCropDrag(start("s"), 0.9, 0.4))
      .toEqual({ x0: 0, y0: 0, x1: 1, y1: 0.4 });
  });

  it("moves both edges of a corner", () => {
    expect(applyCropDrag(start("se"), 0.6, 0.7))
      .toEqual({ x0: 0, y0: 0, x1: 0.6, y1: 0.7 });
    expect(applyCropDrag(start("nw"), 0.2, 0.3))
      .toEqual({ x0: 0.2, y0: 0.3, x1: 1, y1: 1 });
  });

  it("stops at the minimum size instead of flipping inside out", () => {
    // Drag the left edge past the right one: it pins one MIN_CROP_FRAC short,
    // and the right edge — which was not grabbed — never moves.
    const out = applyCropDrag(start("w", { x0: 0, y0: 0, x1: 0.5, y1: 1 }), 0.9, 0.5);
    expect(out.x1).toBe(0.5);
    expect(out.x0).toBeCloseTo(0.5 - MIN_CROP_FRAC, 10);
    expect(out.x1 - out.x0).toBeCloseTo(MIN_CROP_FRAC, 10);
  });

  it("clamps a drag beyond the frame to the frame", () => {
    const out = applyCropDrag(start("ne", { x0: 0.2, y0: 0.2, x1: 0.4, y1: 0.4 }), 5, -5);
    expect(out).toEqual({ x0: 0.2, y0: 0, x1: 1, y1: 0.4 });
  });
});

describe("applyCropDrag — move", () => {
  const c = { x0: 0.2, y0: 0.2, x1: 0.6, y1: 0.5 };

  it("slides the rectangle by the pointer delta, keeping its size", () => {
    const out = applyCropDrag(start("move", c, 0.4, 0.35), 0.5, 0.45);
    expect(out.x0).toBeCloseTo(0.3, 10);
    expect(out.y0).toBeCloseTo(0.3, 10);
    expect(out.x1 - out.x0).toBeCloseTo(0.4, 10);
    expect(out.y1 - out.y0).toBeCloseTo(0.3, 10);
  });

  it("parks against the border with its size preserved rather than squashing", () => {
    const out = applyCropDrag(start("move", c, 0.4, 0.35), 5, 5);
    expect(out.x1).toBeCloseTo(1, 10);
    expect(out.y1).toBeCloseTo(1, 10);
    expect(out.x1 - out.x0).toBeCloseTo(0.4, 10);
    expect(out.y1 - out.y0).toBeCloseTo(0.3, 10);
  });

  it("parks against the top-left corner the same way", () => {
    const out = applyCropDrag(start("move", c, 0.4, 0.35), -5, -5);
    expect(out.x0).toBe(0);
    expect(out.y0).toBe(0);
    expect(out.x1 - out.x0).toBeCloseTo(0.4, 10);
    expect(out.y1 - out.y0).toBeCloseTo(0.3, 10);
  });

  it("is a no-op when the pointer hasn't moved", () => {
    expect(applyCropDrag(start("move", c, 0.4, 0.35), 0.4, 0.35)).toEqual(c);
  });
});

describe("cropHandlePositions", () => {
  it("places all eight handles on the rectangle's edges and corners", () => {
    const pos = cropHandlePositions({ x0: 0.2, y0: 0.4, x1: 0.6, y1: 0.8 });
    expect(pos.map((p) => p.handle))
      .toEqual(["nw", "n", "ne", "e", "se", "s", "sw", "w"]);
    const by = Object.fromEntries(pos.map((p) => [p.handle, p]));
    expect(by.nw).toMatchObject({ left: "20.00%", top: "40.00%", cursor: "nwse-resize" });
    expect(by.se).toMatchObject({ left: "60.00%", top: "80.00%", cursor: "nwse-resize" });
    // Edge handles sit at the midpoint of their side.
    expect(by.n).toMatchObject({ left: "40.00%", top: "40.00%", cursor: "ns-resize" });
    expect(by.e).toMatchObject({ left: "60.00%", top: "60.00%", cursor: "ew-resize" });
  });

  it("gives every handle a resize cursor (nothing renders as a plain arrow)", () => {
    for (const p of cropHandlePositions(FULL_CROP)) {
      expect(p.cursor).toMatch(/resize$/);
    }
  });
});

describe("cropKeptLabel / isFullFrame", () => {
  it("says nothing is being cut when the rectangle is the whole frame", () => {
    expect(isFullFrame(FULL_CROP)).toBe(true);
    expect(cropKeptLabel(FULL_CROP)).toBe("Keeping the whole picture");
  });

  it("reports each axis, not the area", () => {
    expect(cropKeptLabel({ x0: 0.1, y0: 0.2, x1: 0.7, y1: 0.8 }))
      .toBe("Keeping 60% × 60% of the picture");
  });

  it("treats a sub-pixel rounding residue as the whole frame", () => {
    expect(isFullFrame({ x0: 0, y0: 0, x1: 0.9995, y1: 1 })).toBe(true);
    expect(isFullFrame({ x0: 0, y0: 0, x1: 0.99, y1: 1 })).toBe(false);
  });
});

describe("bigCropNote", () => {
  it("stays quiet on an ordinary crop", () => {
    expect(bigCropNote(FULL_CROP)).toBeNull();
    expect(bigCropNote({ x0: 0.1, y0: 0.1, x1: 0.9, y1: 0.9 })).toBeNull();
    // Exactly at the threshold (50% × 50% = 25% of the area) is still quiet.
    expect(bigCropNote({ x0: 0.25, y0: 0.25, x1: 0.75, y1: 0.75 })).toBeNull();
  });

  it("speaks up once the crop takes a real bite out of the frame", () => {
    const note = bigCropNote({ x0: 0.4, y0: 0.4, x1: 0.6, y1: 0.6 });
    expect(note).toContain("big crop");
    expect(note).toContain("smaller");
  });

  it("says nothing about a degenerate rectangle", () => {
    expect(bigCropNote({ x0: 0.5, y0: 0.5, x1: 0.5, y1: 0.5 })).toBeNull();
  });
});

describe("existingCropUid", () => {
  it("answers null for a recipe with no crop", () => {
    expect(existingCropUid([op("s", "tone.stretch")])).toBeNull();
    expect(existingCropUid([])).toBeNull();
  });

  it("finds the recipe's crop so a second one is never stacked on it", () => {
    expect(existingCropUid([op("s", "tone.stretch"), op("c", "geometry.crop")])).toBe("c");
  });

  it("prefers an enabled crop over a disabled leftover", () => {
    expect(existingCropUid([op("off", "geometry.crop", false),
                            op("on", "geometry.crop", true)])).toBe("on");
  });

  it("still finds a crop that is only disabled", () => {
    expect(existingCropUid([op("off", "geometry.crop", false)])).toBe("off");
  });
});

describe("cropDragBlockedReason", () => {
  const crop = op("c", "geometry.crop");

  it("allows dragging when the crop is the last geometry op", () => {
    expect(cropDragBlockedReason(
      [op("s", "tone.stretch"), crop, op("t", "tone.saturation")], "c")).toBeNull();
  });

  it("allows dragging when the other geometry ops come before it", () => {
    expect(cropDragBlockedReason(
      [op("r", "geometry.rotate"), op("z", "geometry.resize"), crop], "c")).toBeNull();
  });

  it("declines when a rotate or resize sits after it", () => {
    expect(cropDragBlockedReason([crop, op("r", "geometry.rotate")], "c"))
      .toContain("Rotate or Resize");
    expect(cropDragBlockedReason([crop, op("z", "geometry.resize")], "c"))
      .toBeTruthy();
  });

  it("declines when a SECOND crop sits after it — the bypassed render would "
     + "then show that crop's output, not this crop's input", () => {
    expect(cropDragBlockedReason([crop, op("c2", "geometry.crop")], "c")).toBeTruthy();
  });

  it("ignores a disabled geometry op after it (it reshapes nothing)", () => {
    expect(cropDragBlockedReason([crop, op("r", "geometry.rotate", false)], "c"))
      .toBeNull();
  });

  it("answers null for an op that isn't in the list", () => {
    expect(cropDragBlockedReason([crop], "nope")).toBeNull();
  });
});
