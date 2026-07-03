import { describe, expect, it } from "vitest";
import { pngProgressLabel } from "./pngProgress";

describe("pngProgressLabel", () => {
  it("shows a percentage when total is known", () => {
    expect(pngProgressLabel({ phase: "Rendering", done: 45, total: 90, detail: "" }))
      .toBe("Rendering — 50%");
  });

  it("clamps the percentage into 0..100", () => {
    expect(pngProgressLabel({ phase: "Rendering", done: 200, total: 100, detail: "" }))
      .toBe("Rendering — 100%");
  });

  it("falls back to the phase name when total is unknown", () => {
    expect(pngProgressLabel({ phase: "Loading frames", done: 0, total: 0, detail: "" }))
      .toBe("Loading frames");
  });

  it("uses a generic label when the phase is blank", () => {
    expect(pngProgressLabel({ phase: "", done: 0, total: 0, detail: "" })).toBe("Rendering");
  });

  it("returns a starting label for a null job", () => {
    expect(pngProgressLabel(null)).toBe("Rendering…");
  });
});
