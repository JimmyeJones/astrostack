import { describe, expect, it } from "vitest";

import { starReduceOverstatesCaption } from "./starReducePreview";

describe("starReduceOverstatesCaption", () => {
  it("returns null for missing/empty input", () => {
    expect(starReduceOverstatesCaption(undefined)).toBeNull();
    expect(starReduceOverstatesCaption(null)).toBeNull();
    expect(starReduceOverstatesCaption({})).toBeNull();
  });

  it("returns null when the flag is false", () => {
    expect(starReduceOverstatesCaption({ star_reduce_preview_overstates: false })).toBeNull();
  });

  it("returns an advisory when the flag is set", () => {
    const cap = starReduceOverstatesCaption({ star_reduce_preview_overstates: true });
    expect(cap).toContain("Star reduction preview overstates");
    expect(cap).toContain("export");
  });
});
