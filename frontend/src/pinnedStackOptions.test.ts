import { describe, expect, it } from "vitest";
import type { PinnedStackOption, StackOptionField } from "./api/client";
import {
  adoptGlobalsPatch, pinnedLine, pinnedSummary, pinnedValueText,
} from "./pinnedStackOptions";

const field = (over: Partial<StackOptionField>): StackOptionField => ({
  key: "k", label: "L", type: "bool", group: "simple", default: null,
  min: null, max: null, step: null, options: null, help: null, depends_on: null,
  ...over,
});

const opt = (over: Partial<PinnedStackOption>): PinnedStackOption => ({
  key: "sigma_clip", label: "Sigma clip", saved: false, global_value: true, ...over,
});

describe("pinnedValueText", () => {
  it("says on/off for a checkbox rather than true/false", () => {
    expect(pinnedValueText(true, field({}))).toBe("on");
    expect(pinnedValueText(false, field({}))).toBe("off");
  });

  it("uses the schema's own caption for an enum, so the note names the control", () => {
    const f = field({
      key: "mosaic_canvas", type: "enum", options: ["auto", "union"],
      option_labels: { auto: "Auto", union: "Union (keep everything)" },
    });
    expect(pinnedValueText("union", f)).toBe("Union (keep everything)");
    // An option the labels don't cover still prints, rather than blanking.
    expect(pinnedValueText("reference", f)).toBe("reference");
  });

  it("falls back to the plain value with no schema loaded", () => {
    expect(pinnedValueText(2.5, undefined)).toBe("2.5");
    expect(pinnedValueText(null, undefined)).toBe("not set");
  });
});

describe("pinnedSummary", () => {
  it("is silent when nothing is pinned — the common case", () => {
    expect(pinnedSummary([])).toBeNull();
    expect(pinnedSummary(undefined)).toBeNull();
  });

  it("counts, and reads correctly in the singular", () => {
    expect(pinnedSummary([opt({})])).toContain("1 saved setting");
    expect(pinnedSummary([opt({})])).toContain("is different");
    const two = pinnedSummary([opt({}), opt({ key: "drizzle", label: "Drizzle" })]);
    expect(two).toContain("2 saved settings");
    expect(two).toContain("are different");
  });
});

describe("pinnedLine", () => {
  it("names the option and both values, here first", () => {
    expect(pinnedLine(opt({ label: "Auto outlier removal" }), [])).toBe(
      "Auto outlier removal: off here, on globally");
  });

  it("reads the enum captions off the schema", () => {
    const fields = [field({
      key: "mosaic_canvas", label: "Canvas mode", type: "enum",
      options: ["auto", "union"], option_labels: { auto: "Auto", union: "Union" },
    })];
    expect(pinnedLine(
      opt({ key: "mosaic_canvas", label: "Canvas mode", saved: "union", global_value: "auto" }),
      fields,
    )).toBe("Canvas mode: Union here, Auto globally");
  });
});

describe("adoptGlobalsPatch", () => {
  it("is one patch of every global value, so the form updates once", () => {
    expect(adoptGlobalsPatch([
      opt({ key: "sigma_clip", saved: false, global_value: true }),
      opt({ key: "sigma_kappa", saved: 2, global_value: 3 }),
    ])).toEqual({ sigma_clip: true, sigma_kappa: 3 });
  });

  it("is empty — never undefined — with nothing pinned", () => {
    expect(adoptGlobalsPatch(undefined)).toEqual({});
  });
});
