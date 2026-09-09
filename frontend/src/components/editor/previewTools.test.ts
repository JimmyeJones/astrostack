import { describe, expect, it } from "vitest";
import { PREVIEW_TOOLS, visiblePreviewTools } from "./previewTools";

describe("visiblePreviewTools", () => {
  it("offers the coverage heatmap only on a mosaic", () => {
    const keys = (o: { isMosaic: boolean; cropDrag: boolean }) =>
      visiblePreviewTools(o).map((t) => t.key);
    expect(keys({ isMosaic: false, cropDrag: false })).not.toContain("coverage");
    expect(keys({ isMosaic: true, cropDrag: false })).toContain("coverage");
  });

  it("offers the crop handles only while a Crop op can take them", () => {
    const keys = (cropDrag: boolean) =>
      visiblePreviewTools({ isMosaic: false, cropDrag }).map((t) => t.key);
    expect(keys(false)).not.toContain("cropDrag");
    expect(keys(true)).toContain("cropDrag");
  });

  it("lists the row in the order the row renders it", () => {
    // The guide reads top-to-bottom against a row that reads left-to-right; a
    // reader matching one to the other should not have to search.
    expect(visiblePreviewTools({ isMosaic: true, cropDrag: true }).map((t) => t.key))
      .toEqual(["coverage", "mask", "cropDrag", "compare", "split", "look",
        "refresh", "zoom"]);
  });

  it("gives every tool a label and a sentence, and never an empty one", () => {
    for (const t of Object.values(PREVIEW_TOOLS)) {
      expect(t.label.length).toBeGreaterThan(0);
      // A hint short enough to be a restatement of the label is not an
      // explanation — this is the whole point of the array.
      expect(t.hint.length).toBeGreaterThan(30);
    }
  });

  it("keys each entry with the name it is filed under", () => {
    for (const [key, t] of Object.entries(PREVIEW_TOOLS)) expect(t.key).toBe(key);
  });
});
