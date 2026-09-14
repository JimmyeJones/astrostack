import { describe, expect, it } from "vitest";

import { deconvUnderstatesCaption } from "./deconvPreview";
import { FULL_SIZE_CHECK_LABEL } from "./loupe";

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

  it("names the control instead of leaving two knobs unjudgeable", () => {
    const cap = deconvUnderstatesCaption({ deconv_preview_understates: true });
    expect(cap).toContain(FULL_SIZE_CHECK_LABEL);
  });

  it("does not invite the reader to change the saved picture to see it", () => {
    // The rule v0.445.3 established across this panel: no advisory may tell the
    // reader to turn a knob up in order to make the preview show something,
    // because a picture judged that way is saved over-processed. Deconvolution's
    // two knobs (Iterations, Blur width) make "turn it up until you can see it"
    // the obvious move, so the caption warns against it by name.
    const cap = deconvUnderstatesCaption({ deconv_preview_understates: true })!;
    expect(cap).toMatch(/turning the iterations up .* harder than you meant/);
    expect(cap).not.toMatch(/raise the (iterations|blur|strength) if you want/i);
  });
});
