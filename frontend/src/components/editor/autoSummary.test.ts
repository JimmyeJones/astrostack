import { describe, expect, it } from "vitest";
import {
  autoSummaryPhrases, autoSummarySentence, autoValuePhrases, autoValueSentence,
} from "./autoSummary";
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

  it("names the mosaic border trim (geometry.crop) in plain language", () => {
    // Auto appends a final crop on a mosaic; the summary must read cleanly, not
    // fall back to a bare "crop".
    const ops = [op("tone.stretch"), op("geometry.crop")];
    expect(autoSummaryPhrases(ops, SPECS)).toEqual([
      "applied a natural stretch", "trimmed the ragged mosaic border",
    ]);
  });

  it("names the gentle contrast curve (tone.curves) in plain language", () => {
    // Auto now appends a tone.curves op (auto contrast) after saturation, so the
    // summary must describe it as a contrast curve, not a bare label.
    const ops = [op("tone.saturation"), op("tone.curves")];
    expect(autoSummaryPhrases(ops, SPECS)).toEqual([
      "boosted colour saturation", "added a gentle contrast curve",
    ]);
  });

  it("names the mosaic coverage-leveling step in plain language", () => {
    // Auto prepends background.level_coverage as its *first* step on a mosaic, so
    // without a phrase the whole summary opens with the jargon label "coverage
    // leveling" — the same gap the geometry.crop phrase closes at the other end.
    const ops = [op("background.level_coverage"), op("tone.stretch")];
    expect(autoSummaryPhrases(ops, SPECS)).toEqual([
      "evened out the mosaic panel brightness", "applied a natural stretch",
    ]);
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

function pop(id: string, params: Record<string, unknown>, enabled = true): OpInstance {
  return { uid: id, id, enabled, params };
}

describe("autoValuePhrases", () => {
  it("reads the data-driven values from the built recipe in pipeline order", () => {
    const ops = [
      pop("background.final_gradient", { mode: "luminance" }),
      pop("detail.denoise", { method: "wavelet", strength: 0.6 }),
      pop("tone.stretch", { mode: "stf", target_bg: 0.2 }),
      pop("tone.saturation", { amount: 1.1 }),
    ];
    expect(autoValuePhrases(ops)).toEqual([
      "denoise strength 0.6", "sky level 0.2", "saturation 1.1×",
    ]);
  });

  it("includes the sharpen radius and formats to at most 2 decimals", () => {
    const ops = [pop("detail.sharpen", { amount: 0.5, radius: 1.35 })];
    expect(autoValuePhrases(ops)).toEqual(["sharpen radius 1.35 px"]);
  });

  it("surfaces the crossfaded sharpen strength when eased below full", () => {
    // A mildly-noisy stack gets a gentler sharpen (amount < 0.5), which the
    // crossfade tuned from the data — so name it alongside the radius.
    const ops = [pop("detail.sharpen", { amount: 0.3, radius: 1.4 })];
    expect(autoValuePhrases(ops)).toEqual(["sharpen radius 1.4 px (strength 0.3)"]);
  });

  it("omits the STF sky level when the stretch is not in STF mode", () => {
    expect(autoValuePhrases([pop("tone.stretch", { mode: "asinh", stretch: 0.5 })])).toEqual([]);
  });

  it("skips disabled and value-less ops", () => {
    const ops = [
      pop("tone.saturation", { amount: 1.2 }, false),
      pop("tone.color_calibrate", { mode: "gray_star" }),
    ];
    expect(autoValuePhrases(ops)).toEqual([]);
  });

  it("skips an op whose value param is missing/non-numeric", () => {
    expect(autoValuePhrases([pop("detail.denoise", {})])).toEqual([]);
  });
});

describe("autoValueSentence", () => {
  it("returns null when no value-bearing op is present", () => {
    expect(autoValueSentence([op("tone.color_calibrate")])).toBeNull();
  });

  it("prefixes the joined values with a plain-language lead", () => {
    const ops = [
      pop("tone.stretch", { mode: "stf", target_bg: 0.2 }),
      pop("tone.saturation", { amount: 1.05 }),
      pop("detail.sharpen", { radius: 1.4 }),
    ];
    expect(autoValueSentence(ops)).toBe(
      "Tuned to your data: sky level 0.2, saturation 1.05×, sharpen radius 1.4 px.",
    );
  });
});
