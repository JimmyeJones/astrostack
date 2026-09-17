import { describe, expect, it } from "vitest";
import type { MosaicPlan } from "./api/client";
import { mosaicDepthHours, mosaicDepthText, mosaicEffortText, withMosaicEffort } from "./mosaicEffort";
import { goalHoursForType } from "./readiness";

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

describe("mosaicDepthText", () => {
  it("prices the grid in hours for a surface with no pace to spend", () => {
    // 9 panels x 4 h (Nebula) = 36 h. This is the sentence the Target page's
    // measured framing verdict adds under "About a 3x3 mosaic (9 panels)".
    const text = mosaicDepthText(plan(3, 3), "Emission nebula");
    expect(text).toBe(
      "Giving all 9 panels the depth you'd give one field (~4 h each) "
      + "is about 36 h of shooting.");
  });

  it("says the same claim as the planner's clear-nights sentence", () => {
    // The two run on one surface each and must not read as two opinions: the
    // shared clause is what makes the hours version recognisable as the same
    // answer the badge gives in nights.
    const clause = "giving all 6 panels the depth you'd give one field";
    expect(mosaicEffortText(plan(3, 2), "Galaxy", 3 * H)).toContain(clause);
    expect(mosaicDepthText(plan(3, 2), "Galaxy")?.toLowerCase()).toContain(clause);
  });

  it("quotes the per-field goal the readiness card is already showing", () => {
    // Not a second definition of "enough for a clean image": the per-field
    // figure in the sentence is `goalHoursForType`, which on a single field is
    // exactly `integrationReadiness`'s own `baseGoalHours`. A curated "easy"
    // verdict moves both together.
    expect(goalHoursForType("Emission nebula")).toBe(4);
    expect(mosaicDepthText(plan(3, 3), "Emission nebula")).toContain("(~4 h each)");
    const easy = { level: "easy", curated: true };
    expect(goalHoursForType("Emission nebula", easy)).toBe(2);
    const text = mosaicDepthText(plan(3, 3), "Emission nebula", easy);
    expect(text).toContain("(~2 h each)");
    expect(text).toContain("about 18 h of shooting");
  });

  it("prints a fractional goal to one decimal rather than raw", () => {
    // 2 panels x 1.5 h (Cluster) = 3 h; the per-field figure is the fraction.
    expect(mosaicDepthText(plan(2, 1), "Open cluster"))
      .toBe("Giving all 2 panels the depth you'd give one field (~1.5 h each) "
        + "is about 3 h of shooting.");
  });

  it("falls back to the mid-range goal for an unrecognised type", () => {
    expect(mosaicDepthText(plan(3, 2), "")).toContain("about 24 h of shooting");
    expect(mosaicDepthText(plan(3, 2), null)).toContain("about 24 h of shooting");
  });

  it("names its own scope on a picture that is already a mosaic", () => {
    // Read in place, this sentence lands third: "adding more panels next session
    // would capture the rest" → "about a 3x3 covers all of it" → the hours. The
    // first two are about what's left, so the third has to say it isn't.
    expect(mosaicDepthText(plan(3, 3), "Emission nebula", undefined,
      { alreadyAMosaic: true }))
      .toBe("Giving all 9 panels the depth you'd give one field (~4 h each) "
        + "is about 36 h of shooting — the whole grid from scratch, not counting "
        + "what this picture already has.");
  });

  it("subtracts nothing, and says nothing extra on an unstarted target", () => {
    // The clause states the assumption; it never claims an hours-remaining
    // figure, because whether the panels already shot even fall inside the
    // proposed grid is not something this arithmetic knows.
    const scoped = mosaicDepthText(plan(3, 3), "Emission nebula", undefined,
      { alreadyAMosaic: true });
    expect(scoped).toContain("about 36 h of shooting");
    // …and every caller that cannot tell keeps today's sentence exactly.
    const plainSentence = "Giving all 9 panels the depth you'd give one field "
      + "(~4 h each) is about 36 h of shooting.";
    expect(mosaicDepthText(plan(3, 3), "Emission nebula")).toBe(plainSentence);
    expect(mosaicDepthText(plan(3, 3), "Emission nebula", undefined, {}))
      .toBe(plainSentence);
    expect(mosaicDepthText(plan(3, 3), "Emission nebula", undefined,
      { alreadyAMosaic: false })).toBe(plainSentence);
  });

  it("says nothing when there is no grid to price", () => {
    expect(mosaicDepthText(null, "Galaxy")).toBeNull();
    expect(mosaicDepthText(undefined, "Galaxy")).toBeNull();
    // A degenerate one-panel "mosaic" is not a project worth pricing — the same
    // silence `mosaicEffortText` has always kept.
    expect(mosaicDepthText(plan(1, 1), "Galaxy")).toBeNull();
    expect(mosaicDepthText({ ...plan(3, 2), panels: Number.NaN }, "Galaxy")).toBeNull();
  });
});

describe("mosaicDepthHours", () => {
  it("is the arithmetic both sentences share", () => {
    expect(mosaicDepthHours(plan(3, 2), "Galaxy")).toEqual(
      { panels: 6, perFieldHours: 6, totalHours: 36 });
  });

  it("multiplies by panels, never by the mosaic's field-fulls of sky", () => {
    // Overlap does not make the job cheaper — the overlapped strips simply end
    // up deeper — so a 3x2 is six times one field however the panels are laid.
    const d = mosaicDepthHours(plan(3, 2), "Emission nebula");
    expect(d?.totalHours).toBe(6 * 4);
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
