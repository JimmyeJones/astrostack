import { describe, expect, it } from "vitest";
import { autoSummaryPhrases, autoSummarySentence } from "./autoSummary";
import type { EditOp, OpInstance } from "../../api/client";

function spec(id: string, label: string): EditOp {
  return {
    id, label, group: "tone", stage: "any", proxy_safe: true, is_stretch: false,
    help: null, params: [],
  };
}

const SPECS: Record<string, EditOp> = {
  "background.final_gradient": spec("background.final_gradient", "Final gradient"),
  "tone.color_calibrate": spec("tone.color_calibrate", "Colour calibrate"),
  "tone.stretch": spec("tone.stretch", "Stretch"),
  "tone.scnr": spec("tone.scnr", "SCNR"),
  "tone.saturation": spec("tone.saturation", "Saturation"),
  "detail.sharpen": spec("detail.sharpen", "Sharpen"),
  "mystery.op": spec("mystery.op", "Mystery Op"),
};

function op(id: string, enabled = true): OpInstance {
  return { uid: id, id, enabled, params: {} };
}

// The default auto recipe (clean image): gradient, colour, stretch, scnr, sat, sharpen.
const AUTO_OPS = [
  op("background.final_gradient"), op("tone.color_calibrate"), op("tone.stretch"),
  op("tone.scnr"), op("tone.saturation"), op("detail.sharpen"),
];

describe("autoSummaryPhrases", () => {
  it("maps each op to its plain-language phrase in order", () => {
    expect(autoSummaryPhrases(AUTO_OPS, SPECS)).toEqual([
      "flattened the background", "balanced the colour", "applied a natural stretch",
      "removed the green cast", "boosted colour saturation", "sharpened detail",
    ]);
  });

  it("skips disabled ops", () => {
    const ops = [op("tone.stretch"), op("tone.scnr", false)];
    expect(autoSummaryPhrases(ops, SPECS)).toEqual(["applied a natural stretch"]);
  });

  it("falls back to the registry label (lower-cased) for unknown ops", () => {
    expect(autoSummaryPhrases([op("mystery.op")], SPECS)).toEqual(["mystery op"]);
  });

  it("falls back to the raw id when no spec is known", () => {
    expect(autoSummaryPhrases([op("ghost.op")], {})).toEqual(["ghost.op"]);
  });

  it("de-duplicates repeated phrases", () => {
    const ops = [op("tone.scnr"), op("tone.scnr")];
    expect(autoSummaryPhrases(ops, SPECS)).toEqual(["removed the green cast"]);
  });
});

describe("autoSummarySentence", () => {
  it("returns null for an empty recipe", () => {
    expect(autoSummarySentence([], SPECS)).toBeNull();
  });

  it("capitalises a single phrase and ends with a period", () => {
    expect(autoSummarySentence([op("tone.stretch")], SPECS)).toBe("Applied a natural stretch.");
  });

  it("joins two phrases with 'then'", () => {
    const ops = [op("tone.stretch"), op("detail.sharpen")];
    expect(autoSummarySentence(ops, SPECS)).toBe("Applied a natural stretch, then sharpened detail.");
  });

  it("joins many phrases with commas and a trailing 'then'", () => {
    expect(autoSummarySentence(AUTO_OPS, SPECS)).toBe(
      "Flattened the background, balanced the colour, applied a natural stretch, "
      + "removed the green cast, boosted colour saturation, then sharpened detail.",
    );
  });
});
