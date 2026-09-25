import { describe, expect, it } from "vitest";

import { gradeCapNotice } from "./gradeCap";

const base = {
  capped: true,
  capped_overall: false,
  capped_panels: 0,
  withheld_per_panel: 0,
};

describe("gradeCapNotice", () => {
  it("says nothing when nothing was capped", () => {
    expect(gradeCapNotice({ ...base, capped: false })).toBeNull();
    expect(gradeCapNotice(null)).toBeNull();
    expect(gradeCapNotice(undefined)).toBeNull();
  });

  it("keeps the rough-session sentence for the target-wide rail", () => {
    const n = gradeCapNotice({ ...base, capped_overall: true });
    expect(n?.kind).toBe("session");
    expect(n?.text).toContain("rough session");
    expect(n?.text).toContain("conservative pass");
  });

  it("does NOT blame the night when only the per-panel rail fired", () => {
    // V772 Herculis: 8.0% of the target flagged, one frame withheld — and the
    // banner used to read "this looks like a rough session".
    const n = gradeCapNotice({
      ...base, capped_panels: 1, withheld_per_panel: 1,
    });
    expect(n?.kind).toBe("panels");
    expect(n?.text).not.toContain("rough session");
    expect(n?.text).not.toContain("night's data");
    expect(n?.text).toContain("1 flagged frame on 1 mosaic panel was held back");
    // …and it says the offered remedy is the wrong lever, because a count limit
    // cannot be released by raising a threshold.
    expect(n?.text).toContain("conservative pass won't release them");
  });

  it("pluralises the panel sentence", () => {
    const n = gradeCapNotice({
      ...base, capped_panels: 9, withheld_per_panel: 56,
    });
    expect(n?.text).toContain("56 flagged frames on 9 mosaic panels were held back");
  });

  it("names both rails when both fired", () => {
    const n = gradeCapNotice({
      ...base, capped_overall: true, capped_panels: 3, withheld_per_panel: 12,
    });
    expect(n?.kind).toBe("both");
    expect(n?.text).toContain("25% safety cap");
    expect(n?.text).toContain("12 flagged frames on 3 mosaic panels");
  });

  it("reads an older backend's bare flag exactly as that install showed it", () => {
    const n = gradeCapNotice({ capped: true } as never);
    expect(n?.kind).toBe("session");
    expect(n?.text).toContain("rough session");
  });
});
