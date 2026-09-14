import { describe, expect, it } from "vitest";

import { hotPixelsSkippedCaption } from "./hotPixelsPreview";
import { FULL_SIZE_CHECK_LABEL } from "./loupe";

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

  it("names the control that does show it, rather than leaving a slider unset", () => {
    // Reassurance without an answer was the gap: this op has a Threshold (σ)
    // slider, and a reader told the preview shows none of its effect has a knob
    // and no way to set it. The full-size check renders at proxy_scale 1, where
    // the op really runs — pinned engine-side in
    // `tests/test_edit_detail_ops.py::test_the_full_size_render_really_does_what_the_advisories_promise`.
    const cap = hotPixelsSkippedCaption({ hot_pixels_preview_skipped: true });
    expect(cap).toContain(FULL_SIZE_CHECK_LABEL);
    expect(cap).toContain("at the threshold you've set");
  });
});
