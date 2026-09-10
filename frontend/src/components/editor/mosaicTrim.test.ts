import { describe, expect, it } from "vitest";
import type { EditOp, OpInstance } from "../../api/client";
import { applyTrimCrop, trimRectStyle, trimKeptLabel, hasEnabledGeometryOp,
  geometryOpsKey, previewBoxStyle, cropCoveragePct, cropCoverageFraction,
  removeCropOps, overTrimmedVerdict, overTrimmedSentence,
  OVER_TRIM_KEEP_RATIO } from "./mosaicTrim";

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

describe("previewBoxStyle", () => {
  it("falls back to plain full-width when proxy dims are unknown", () => {
    expect(previewBoxStyle(undefined, undefined))
      .toEqual({ width: "100%", maxHeight: "62vh" });
    expect(previewBoxStyle(0, 100)).toEqual({ width: "100%", maxHeight: "62vh" });
    expect(previewBoxStyle(NaN, 100)).toEqual({ width: "100%", maxHeight: "62vh" });
  });

  it("sizes the box to the image aspect ratio and caps its width by height", () => {
    // A portrait frame (3:4) — the box carries the image's own aspect ratio and
    // a width cap so the aspect-preserved height never exceeds 62vh; no maxHeight
    // (and thus no letterbox) so a percentage overlay lines up.
    const s = previewBoxStyle(600, 800);
    expect(s.aspectRatio).toBe("600 / 800");
    expect(s.maxWidth).toBe("calc(62vh * 600 / 800)");
    expect(s.margin).toBe("0 auto");
    expect(s.maxHeight).toBeUndefined();
  });

  it("honours a custom max-height", () => {
    expect(previewBoxStyle(1000, 500, 50).maxWidth).toBe("calc(50vh * 1000 / 500)");
  });
});

describe("trimKeptLabel", () => {
  it("summarises the kept fraction in plain language", () => {
    expect(trimKeptLabel(crop)).toBe("keeps the central 60% × 80%");
  });
});

describe("hasEnabledGeometryOp", () => {
  const op = (id: string, enabled: boolean): OpInstance =>
    ({ uid: id, id, enabled, params: {} });

  it("detects an enabled crop/rotate/resize op", () => {
    expect(hasEnabledGeometryOp([op("geometry.crop", true)])).toBe(true);
    expect(hasEnabledGeometryOp([op("geometry.rotate", true)])).toBe(true);
  });

  it("ignores a disabled geometry op and non-geometry ops", () => {
    expect(hasEnabledGeometryOp([op("geometry.crop", false)])).toBe(false);
    expect(hasEnabledGeometryOp([op("tone.stretch", true)])).toBe(false);
    expect(hasEnabledGeometryOp([])).toBe(false);
  });
});

describe("cropCoveragePct / cropCoverageFraction", () => {
  const op = (id: string, enabled: boolean,
              params: Record<string, unknown> = {}): OpInstance =>
    ({ uid: id, id, enabled, params });

  it("returns null when there's no enabled crop", () => {
    expect(cropCoveragePct([])).toBeNull();
    expect(cropCoveragePct([op("tone.stretch", true, { stretch: 0.5 })])).toBeNull();
    // A disabled crop isn't shrinking the view.
    expect(cropCoveragePct([op("geometry.crop", false, { x0: 0.2, x1: 0.8 })])).toBeNull();
  });

  it("returns null when the crop keeps the whole frame (nothing to flag)", () => {
    expect(cropCoveragePct([op("geometry.crop", true, { x0: 0, y0: 0, x1: 1, y1: 1 })]))
      .toBeNull();
  });

  it("reports the kept percentage of a single crop", () => {
    // keeps 60% × 80% = 48%
    expect(cropCoveragePct([op("geometry.crop", true, crop)])).toBe(48);
    expect(cropCoverageFraction([op("geometry.crop", true, crop)]))
      .toBeCloseTo(0.48, 6);
  });

  it("multiplies successive crops (each relative to its input)", () => {
    const half = { x0: 0.25, y0: 0.25, x1: 0.75, y1: 0.75 }; // 25% area each
    const out = cropCoveragePct([op("geometry.crop", true, half),
                                 op("geometry.crop", true, half)]);
    expect(out).toBe(6); // 0.25 * 0.25 = 0.0625 → 6%
  });

  it("mirrors the engine's clamp + sort of out-of-order / out-of-range bounds", () => {
    // x's reversed and beyond [0,1] → clamps then sorts to keep 0..0.8 × 0..1
    const out = cropCoverageFraction(
      [op("geometry.crop", true, { x0: 0.8, x1: -0.5, y0: 0, y1: 2 })]);
    expect(out).toBeCloseTo(0.8, 6);
  });

  it("treats a missing/garbage bound as its default (no crop on that axis)", () => {
    // only y is cropped to 50%; x defaults to full frame
    expect(cropCoveragePct([op("geometry.crop", true, { y0: 0.25, y1: 0.75 })])).toBe(50);
    expect(cropCoveragePct([op("geometry.crop", true, { x0: "oops" as unknown as number,
      x1: 0.5 })])).toBe(50);
  });
});

describe("removeCropOps", () => {
  const op = (id: string, enabled: boolean,
              params: Record<string, unknown> = {}): OpInstance =>
    ({ uid: id, id, enabled, params });

  it("drops enabled crop ops but keeps everything else (incl. a disabled crop)", () => {
    const ops = [
      op("tone.stretch", true, { stretch: 0.5 }),
      op("geometry.crop", true, crop),
      op("geometry.crop", false, crop),
      op("geometry.rotate", true, { angle: 5 }),
    ];
    const out = removeCropOps(ops);
    expect(out.map((o) => `${o.id}:${o.enabled}`)).toEqual([
      "tone.stretch:true", "geometry.crop:false", "geometry.rotate:true",
    ]);
    // pure — input untouched
    expect(ops).toHaveLength(4);
  });
});

describe("geometryOpsKey", () => {
  const op = (id: string, enabled: boolean,
              params: Record<string, unknown> = {}): OpInstance =>
    ({ uid: id, id, enabled, params });

  it("keys only on enabled geometry ops (id + params)", () => {
    const k = geometryOpsKey([
      op("tone.stretch", true, { stretch: 0.5 }),
      op("geometry.crop", true, { x0: 0.1, x1: 0.9 }),
    ]);
    expect(k).toBe(JSON.stringify([{ id: "geometry.crop", params: { x0: 0.1, x1: 0.9 } }]));
  });

  it("changes when a geometry param changes but not when a tone op changes", () => {
    const a = geometryOpsKey([op("geometry.crop", true, { x0: 0.1 }),
                              op("tone.stretch", true, { stretch: 0.5 })]);
    const b = geometryOpsKey([op("geometry.crop", true, { x0: 0.2 }),
                              op("tone.stretch", true, { stretch: 0.5 })]);
    const c = geometryOpsKey([op("geometry.crop", true, { x0: 0.1 }),
                              op("tone.stretch", true, { stretch: 0.9 })]);
    expect(a).not.toBe(b);   // geometry change → new key
    expect(a).toBe(c);       // tone-only change → same key
  });

  it("ignores disabled geometry ops and is empty with none", () => {
    expect(geometryOpsKey([op("geometry.crop", false, { x0: 0.1 })])).toBe("[]");
    expect(geometryOpsKey([op("tone.stretch", true)])).toBe("[]");
    expect(geometryOpsKey([])).toBe("[]");
  });
});

describe("overTrimmedVerdict", () => {
  const op = (params: Record<string, unknown>, enabled = true): OpInstance =>
    ({ uid: "c", id: "geometry.crop", enabled, params });
  // The fourth external audit's reproduction, to the numbers it recorded: a
  // v0.277.0 recipe keeping 3.4% of the canvas while today's border rule keeps
  // 92.4% of it.
  const savedSliver = op({ x0: 0.6228, y0: 0.0341, x1: 0.6896, y1: 0.5463 });
  const honestTrim = { x0: 0.02, y0: 0.02, x1: 0.98, y1: 0.98 };

  it("names the old over-trim with both shares, honestly rounded", () => {
    const v = overTrimmedVerdict([savedSliver], honestTrim);
    expect(v).not.toBeNull();
    expect(v!.keptLabel).toBe("about 3%");   // the audit's 3.4%
    expect(v!.availableLabel).toBe("about 92%");
    expect(overTrimmedSentence(v!)).toContain("about 3% of the stack");
    expect(overTrimmedSentence(v!)).toContain("about 92% of it is well covered");
    expect(overTrimmedSentence(v!)).toContain("Re-trim border");
  });

  it("does not round a sliver up to a percent it does not have", () => {
    const hair = op({ x0: 0.5, y0: 0.5, x1: 0.55, y1: 0.55 });   // 0.25%
    expect(overTrimmedVerdict([hair], honestTrim)!.keptLabel).toBe("under 1%");
  });

  it("says nothing on a single field, where the over-trim never happened", () => {
    // `/editor/trim-suggestion` returns a null crop for a single-field stack, so
    // the tightest crop in the world cannot reach this on one.
    expect(overTrimmedVerdict([savedSliver], null)).toBeNull();
    expect(overTrimmedVerdict([savedSliver], undefined)).toBeNull();
  });

  it("says nothing about a crop that is a framing decision", () => {
    // Cropping in on the middle 40% of a mosaic is a choice, and is exactly why
    // the bar is a quarter rather than a half: at 0.5 this would be accused.
    const framed = op({ x0: 0.2, y0: 0.2, x1: 0.83, y1: 0.83 });   // ~40%
    expect(overTrimmedVerdict([framed], honestTrim)).toBeNull();
    expect(0.4).toBeGreaterThan(OVER_TRIM_KEEP_RATIO * 0.92);
  });

  it("says nothing when there is no enabled crop to be wrong", () => {
    expect(overTrimmedVerdict([], honestTrim)).toBeNull();
    expect(overTrimmedVerdict([op({ x0: 0.62, y0: 0.03, x1: 0.69, y1: 0.55 },
                                  false)], honestTrim)).toBeNull();
  });

  it("is measured against what the canvas offers, not against the whole frame", () => {
    // A genuinely ragged mosaic whose honest rule keeps only 20%: a crop keeping
    // 10% of the frame is then half of what is available, not a sliver of it, so
    // the same crop that fires against a 92% canvas is silent here.
    const ragged = { x0: 0.3, y0: 0.3, x1: 0.75, y1: 0.75 };       // ~20%
    const tenth = op({ x0: 0.35, y0: 0.35, x1: 0.67, y1: 0.67 });  // ~10%
    expect(overTrimmedVerdict([tenth], ragged)).toBeNull();
    expect(overTrimmedVerdict([tenth], honestTrim)).not.toBeNull();
  });

  it("refuses a degenerate suggestion rather than dividing by nothing", () => {
    expect(overTrimmedVerdict([savedSliver],
                              { x0: 0.5, y0: 0.5, x1: 0.5, y1: 0.5 })).toBeNull();
  });
});
