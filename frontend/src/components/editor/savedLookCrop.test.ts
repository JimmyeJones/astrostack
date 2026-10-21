import { describe, expect, it } from "vitest";

import type { OpInstance } from "../../api/client";
import { dropSavedCrop } from "./savedLookCrop";

const op = (id: string, params: Record<string, unknown> = {}, enabled = true): OpInstance =>
  ({ uid: id, id, enabled, params }) as OpInstance;

describe("dropSavedCrop", () => {
  it("drops a saved look's crop and keeps everything else in order", () => {
    const ops = [op("tone.stretch", { stretch: 0.6 }),
      op("geometry.crop", { x0: 0.15, y0: 0.12, x1: 0.85, y1: 0.9 }),
      op("geometry.rotate", { angle: 10 })];
    const out = dropSavedCrop(ops);
    expect(out.dropped).toBe(true);
    expect(out.ops.map((o) => o.id)).toEqual(["tone.stretch", "geometry.rotate"]);
  });

  it("drops a disabled crop too — enabling it later would replay the foreign rectangle", () => {
    const out = dropSavedCrop([op("geometry.crop", { x0: 0.2 }, false)]);
    expect(out).toEqual({ ops: [], dropped: true });
  });

  it("leaves a crop-free look exactly as it was", () => {
    const ops = [op("tone.stretch", { stretch: 0.6 }), op("color.saturation")];
    const out = dropSavedCrop(ops);
    expect(out.dropped).toBe(false);
    expect(out.ops).toEqual(ops);
  });
});
