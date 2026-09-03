import { describe, expect, it } from "vitest";
import type { MosaicPlan } from "./api/client";
import { mosaicEffortText, withMosaicEffort } from "./mosaicEffort";

const H = 3600;

function plan(cols: number, rows: number): MosaicPlan {
  return {
    cols, rows, panels: cols * rows,
    text: `About a ${cols}×${rows} mosaic (${cols * rows} panels) covers all of it.`,
  };
}

describe("mosaicEffortText", () => {
  it("turns the panel count into clear nights at the owner's own pace", () => {
    // 6 panels × 4 h (Nebula) = 24 h, at 3 h a clear night → 8 nights.
    const text = mosaicEffortText(plan(3, 2), "Emission nebula", 3 * H);
    expect(text).toContain("giving all 6 panels the depth you'd give one field");
    expect(text).toContain("about 8 clear nights");
    // The pace is named, so the number is never a mystery.
    expect(text).toContain("~3.0 h of kept subs per clear night");
  });

  it("uses the object type's own goal, not one flat number", () => {
    // A cluster needs 1.5 h a field, so the same grid is a far shorter project
    // than the nebula above — the whole point of reading the type.
    const cluster = mosaicEffortText(plan(3, 2), "Open cluster", 3 * H);
    expect(cluster).toContain("about 3 clear nights");
    const galaxy = mosaicEffortText(plan(3, 2), "Galaxy", 3 * H);
    expect(galaxy).toContain("about 12 clear nights");
  });

  it("says 'night' in the singular when one night would do it", () => {
    // 2 panels × 1.5 h = 3 h, and this owner keeps 4 h a night.
    const text = mosaicEffortText(plan(2, 1), "Globular cluster", 4 * H);
    expect(text).toContain("is about 1 clear night of shooting");
    expect(text).not.toContain("nights");
  });

  it("falls back to the mid-range goal for an unrecognised type", () => {
    // Same as Nebula's 4 h — a target with no catalog match still gets a steer.
    expect(mosaicEffortText(plan(3, 2), "", 3 * H))
      .toContain("about 8 clear nights");
    expect(mosaicEffortText(plan(3, 2), null, 3 * H))
      .toContain("about 8 clear nights");
  });

  it("stays silent for a first-timer with no measured pace", () => {
    expect(mosaicEffortText(plan(3, 2), "Galaxy", null)).toBeNull();
    expect(mosaicEffortText(plan(3, 2), "Galaxy", undefined)).toBeNull();
    // An older backend that sends nothing, and a nonsense pace, are the same
    // silence rather than a divide-by-zero.
    expect(mosaicEffortText(plan(3, 2), "Galaxy", 0)).toBeNull();
    expect(mosaicEffortText(plan(3, 2), "Galaxy", -1)).toBeNull();
    expect(mosaicEffortText(plan(3, 2), "Galaxy", Number.NaN)).toBeNull();
  });

  it("says nothing when there is no mosaic to cost", () => {
    expect(mosaicEffortText(null, "Galaxy", 3 * H)).toBeNull();
    expect(mosaicEffortText(undefined, "Galaxy", 3 * H)).toBeNull();
    // A degenerate one-panel "mosaic" is not a project worth pricing.
    expect(mosaicEffortText(plan(1, 1), "Galaxy", 3 * H)).toBeNull();
  });
});

describe("withMosaicEffort", () => {
  const badge = { label: "Needs 3×2 mosaic", color: "orange", tooltip: "This target is bigger than one frame." };

  it("appends the clause to the badge's existing hover", () => {
    const out = withMosaicEffort(badge, plan(3, 2), "Nebula", 3 * H);
    expect(out?.label).toBe(badge.label);
    expect(out?.color).toBe(badge.color);
    expect(out?.tooltip).toContain("This target is bigger than one frame.");
    expect(out?.tooltip).toContain("about 8 clear nights");
  });

  it("hands the badge back untouched when there is nothing to add", () => {
    // Same object identity: an owner with no pace sees exactly today's tooltip.
    expect(withMosaicEffort(badge, plan(3, 2), "Nebula", null)).toBe(badge);
    expect(withMosaicEffort(badge, null, "Nebula", 3 * H)).toBe(badge);
  });

  it("never invents a badge where the framing hint gave none", () => {
    expect(withMosaicEffort(null, plan(3, 2), "Nebula", 3 * H)).toBeNull();
  });
});
