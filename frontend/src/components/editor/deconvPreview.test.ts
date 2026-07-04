import { describe, expect, it } from "vitest";

import { deconvUnderstatesCaption } from "./deconvPreview";

describe("deconvUnderstatesCaption", () => {
  it("returns null for missing/empty input", () => {
    expect(deconvUnderstatesCaption(undefined)).toBeNull();
    expect(deconvUnderstatesCaption(null)).toBeNull();
    expect(deconvUnderstatesCaption({})).toBeNull();
  });

  it("returns null when the flag is false", () => {
    expect(deconvUnderstatesCaption({ deconv_preview_understates: false })).toBeNull();
  });

  it("returns an advisory when the flag is set", () => {
    const cap = deconvUnderstatesCaption({ deconv_preview_understates: true });
    expect(cap).toContain("Deconvolution preview understates");
    expect(cap).toContain("full strength");
  });
});
