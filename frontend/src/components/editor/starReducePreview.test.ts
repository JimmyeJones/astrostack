import { describe, expect, it } from "vitest";

import { starReduceDiffersCaption } from "./starReducePreview";

describe("starReduceDiffersCaption", () => {
  it("returns null for missing/empty input", () => {
    expect(starReduceDiffersCaption(undefined)).toBeNull();
    expect(starReduceDiffersCaption(null)).toBeNull();
    expect(starReduceDiffersCaption({})).toBeNull();
  });

  it("returns null when the flag is false", () => {
    expect(starReduceDiffersCaption({ star_reduce_preview_overstates: false })).toBeNull();
  });

  it("returns an advisory when the flag is set", () => {
    const cap = starReduceDiffersCaption({ star_reduce_preview_overstates: true });
    expect(cap).toContain("Star reduction looks different");
    expect(cap).toContain("export");
  });

  it("claims no direction — measurement showed the preview goes both ways", () => {
    // The old caption told the user the export would keep their stars *larger*.
    // Measured across star sizes 1-4 and proxy steps 2-5 the preview lands
    // 0.63x-1.58x the export's reduction with no consistent sign at the default
    // size, so any directional word here would be wrong about as often as right.
    const cap = starReduceDiffersCaption({ star_reduce_preview_overstates: true }) ?? "";
    expect(cap).not.toMatch(/overstates|understates|more than|less than|larger|smaller/);
  });
});
