import { describe, expect, it } from "vitest";

import { sharpenUnderstatesCaption } from "./sharpenPreview";

describe("sharpenUnderstatesCaption", () => {
  it("returns null for missing/empty input", () => {
    expect(sharpenUnderstatesCaption(undefined)).toBeNull();
    expect(sharpenUnderstatesCaption(null)).toBeNull();
    expect(sharpenUnderstatesCaption({})).toBeNull();
  });

  it("returns null when the flag is false", () => {
    expect(sharpenUnderstatesCaption({ sharpen_preview_understates: false })).toBeNull();
  });

  it("returns an advisory when the flag is set", () => {
    const cap = sharpenUnderstatesCaption({ sharpen_preview_understates: true });
    expect(cap).toContain("Sharpening preview understates");
    // It must say the export is unaffected, so the user doesn't over-correct.
    expect(cap).toContain("full strength");
  });
});
