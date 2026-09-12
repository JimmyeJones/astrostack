import { describe, expect, it } from "vitest";

import { denoiseUnderstatesCaption } from "./denoisePreview";

describe("denoiseUnderstatesCaption", () => {
  it("returns null for missing/empty input", () => {
    // The empty case is also what an older backend looks like: a build that
    // predates the flag must simply not caption, never caption "unknown".
    expect(denoiseUnderstatesCaption(undefined)).toBeNull();
    expect(denoiseUnderstatesCaption(null)).toBeNull();
    expect(denoiseUnderstatesCaption({})).toBeNull();
  });

  it("returns null when the flag is false", () => {
    expect(denoiseUnderstatesCaption({ denoise_preview_understates: false })).toBeNull();
  });

  it("returns an advisory naming the direction and the safe alternative", () => {
    const cap = denoiseUnderstatesCaption({ denoise_preview_understates: true });
    expect(cap).toContain("previews weaker than it exports");
    // The whole point is the direction: the saved picture is the *smoother* one,
    // so it has to say not to chase the preview with the strength slider.
    expect(cap).toContain("smoother than this");
    expect(cap).toContain("Don't raise the strength");
    // ...and it names the method that has no such gap, since that is the action.
    expect(cap).toContain("Wavelet");
  });
});
