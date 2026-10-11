import { describe, expect, it } from "vitest";
import { unvouchedOpsCaption } from "./windowFidelity";

describe("unvouchedOpsCaption", () => {
  it("says nothing when every op in the recipe renders the window faithfully", () => {
    // The common case, Auto's own recipe included — and the editor's standing
    // complaint is that it is too busy, so the quiet picture pays nothing.
    expect(unvouchedOpsCaption({ unvouched_ops: [] })).toBeNull();
    expect(unvouchedOpsCaption({})).toBeNull();
    expect(unvouchedOpsCaption(undefined)).toBeNull();
    expect(unvouchedOpsCaption(null)).toBeNull();
  });

  it("names the one op, in the singular", () => {
    const text = unvouchedOpsCaption({ unvouched_ops: ["Noise reduction"] });
    expect(text).toContain("Noise reduction measures your whole picture's");
    expect(text).toContain("it has to measure the piece instead");
    expect(text).toContain("how strong it looks here can differ from your export");
    // And what it is *not* saying, which is the half that keeps the control worth
    // opening: every other op renders the window exactly as the export does.
    expect(text).toContain("Every other step here is applying exactly what your export will.");
  });

  it("names several in the plural, with the list read as a sentence", () => {
    const text = unvouchedOpsCaption({
      unvouched_ops: ["Hot-pixel removal", "Noise reduction", "Deconvolution"],
    });
    expect(text).toContain(
      "Hot-pixel removal, Noise reduction and Deconvolution measure your whole picture's");
    expect(text).toContain("they have to measure the piece instead");
    expect(text).toContain("how strong they look here can differ from your export");
    // No stray "and" before a two-item list, and no comma after the last name.
    expect(text).not.toContain("Deconvolution,");
  });

  it("joins exactly two with 'and' and no comma", () => {
    expect(unvouchedOpsCaption({ unvouched_ops: ["Noise reduction", "Deconvolution"] }))
      .toContain("Noise reduction and Deconvolution measure");
  });

  it("ignores blanks and non-strings a backend might send", () => {
    // The names land in a sentence shown to the reader; a bare comma or a
    // dangling "and" is worse than not warning at all.
    const info = { unvouched_ops: ["", "  ", null, 7, "Deconvolution"] as unknown as string[] };
    expect(unvouchedOpsCaption(info)).toContain("Deconvolution measures your whole picture's");
    expect(unvouchedOpsCaption({ unvouched_ops: ["", " "] as string[] })).toBeNull();
  });
});
