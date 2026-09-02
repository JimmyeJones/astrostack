import { describe, expect, it } from "vitest";

import { hotPixelsSkippedCaption } from "./hotPixelsPreview";

describe("hotPixelsSkippedCaption", () => {
  it("returns null for missing/empty input", () => {
    expect(hotPixelsSkippedCaption(undefined)).toBeNull();
    expect(hotPixelsSkippedCaption(null)).toBeNull();
    expect(hotPixelsSkippedCaption({})).toBeNull();
  });

  it("returns null when the flag is false", () => {
    expect(hotPixelsSkippedCaption({ hot_pixels_preview_skipped: false })).toBeNull();
  });

  it("reassures that the export still gets the cleanup", () => {
    const cap = hotPixelsSkippedCaption({ hot_pixels_preview_skipped: true });
    expect(cap).toContain("Hot-pixel removal isn't shown");
    // The reassurance is the point: the op is not off, just not previewable.
    expect(cap).toContain("still gets the cleanup");
  });
});
