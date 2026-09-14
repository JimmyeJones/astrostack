import { describe, expect, it } from "vitest";

import { FULL_SIZE_CHECK_LABEL } from "./loupe";
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

  it("does not tell the reader to change the picture in order to see it", () => {
    // It used to close with "Raise the radius if you want to judge it here."
    // That is the one instruction on this panel that trades the saved picture
    // for a readable preview — and the identical limitation one caption below
    // says the opposite ("Don't raise the strength to make the preview look
    // clean"). A beginner cannot hold both, and the one that costs them is
    // this one: 1.5 px raised to 4 px previews nicely and saves halos.
    const cap = sharpenUnderstatesCaption({ sharpen_preview_understates: true }) ?? "";
    expect(cap).not.toMatch(/raise the radius if/i);
    // The answer instead: the control that shows the export's own pixels.
    expect(cap).toContain(FULL_SIZE_CHECK_LABEL);
  });
});
